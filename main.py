import numpy as np
import torch
from utils.DataLoader import *

from torch.autograd import Variable
import torch.nn as nn
from model.reconNet import ReconNet
import torch.optim as optim
import torch.optim.lr_scheduler as s
import torch.nn.functional as F


# Dataset Parameters
load_size =256
fine_size = 224
data_mean = np.asarray([0.485, 0.456, 0.406,0])
batch_size = 20
voxel_size = 256

# Training Parameters
learning_rate = 0.0001
training_epoches = 10
step_display = 10
step_save = 1
path_save = 'recon0'
start_from = ''#'./alexnet64/Epoch28'
starting_num = 1


# Construct dataloader
opt_data_train = {
    'img_root': 'data/train_imgs/',   # MODIFY PATH ACCORDINGLY
    'voxel_root': 'data/train_voxels/',   # MODIFY PATH ACCORDINGLY
    'load_size': load_size,
    'fine_size': fine_size,
    'voxel_size': voxel_size,
    'data_mean': data_mean,
    'randomize': True,
    'down_sample_scale':8

    }
opt_data_val = {
    'img_root': 'data/val_imgs/',   # MODIFY PATH ACCORDINGLY
    'voxel_root': 'data/val_voxels/',   # MODIFY PATH ACCORDINGLY
    'load_size': load_size,
    'fine_size': fine_size,
    'voxel_size': voxel_size,
    'data_mean': data_mean,
    'randomize': True,
    'down_sample_scale':8

    }

def evaluate_voxel_prediction(prediction,gt):
  """  The prediction and gt are 3 dim voxels. Each voxel has values 1 or 0"""

  intersection = np.sum(np.logical_and(prediction,gt))
  union = np.sum(np.logical_or(prediction,gt))
  IoU = intersection / union

  return IoU

def get_accuracy(loader, size, net):
    sumup = 0

    for i in range(size):
        inputs, labels = loader.next_batch(1)
        inputs = np.swapaxes(inputs,1,3)
        inputs = np.swapaxes(inputs,2,3)
        inputs = torch.from_numpy(inputs).float().cuda()

        net.eval()
        outputs = net(Variable(inputs))


        outputs = outputs.cpu().data.numpy()
        # print("pre1",outputs,np.shape(outputs))

        # print("pre1.5",np.max(outputs, axis=1))

        outputs = np.argmax(outputs, axis=1)
        # print("pre2",outputs,np.shape(outputs))

        # outputs = np.reshape(outputs,[1, 32,32,32])
        labels = np.reshape(labels,[1,32,1024]).astype(int)

        # print(np.shape(outputs),np.shape(labels))

        sumup += evaluate_voxel_prediction(outputs,labels)

    return sumup/size

def weights_init(m):
    classname = m.__class__.__name__
    if classname.find('Conv2') != -1:
        nn.init.kaiming_uniform(m.weight.data)

class CrossEntropyLoss2d(nn.Module):
    def __init__(self, weight=None, size_average=False, ignore_index=-100):
        super(CrossEntropyLoss2d, self).__init__()
        self.nll_loss = nn.NLLLoss2d(size_average = size_average)

    def forward(self, inputs, targets):
        return self.nll_loss(F.log_softmax(inputs), targets)



loader_train = DataLoaderDisk(**opt_data_train)
loader_val = DataLoaderDisk(**opt_data_val)

net = ReconNet()
net = net.cuda()
if start_from != '':
    net.load_state_dict(torch.load(start_from))
else:
    net.apply(weights_init)

# criterion = nn.MSELoss().cuda()
# criterion = nn.NLLLoss2d().cuda()
criterion = CrossEntropyLoss2d(size_average=True).cuda()


optimizer = optim.SGD(net.parameters(), lr=learning_rate, momentum=0.8, weight_decay=0.005) 
scheduler = s.StepLR(optimizer, step_size=1, gamma=0.1)

running_loss = 0.0

if start_from == '':
    with open('./' + path_save + '/log.txt', 'w') as f:
        f.write('')

for epoch in range(training_epoches):
    scheduler.step()
    net.train()

    for i in range(1400):  # loop over the dataset multiple times
        data = loader_train.next_batch(batch_size)

        # get the inputs
        inputs, labels = data
        labels = np.asarray(labels,dtype=np.float32)

        inputs = np.swapaxes(inputs,1,3)
        inputs = np.swapaxes(inputs,2,3)
        inputs = torch.from_numpy(inputs).float()
        labels = torch.from_numpy(labels).long()

        # wrap them in Variable
        # inputs, labels = Variable(inputs), Variable(labels)
        inputs, labels= Variable(inputs.cuda()), Variable(labels.cuda())


        # zero the parameter gradients
        optimizer.zero_grad()

        # forward + backward + optimize # 60*2*32*1024
        output = net(inputs) # places output

        # output = F.log_softmax(output)
        # output = output.view(batch_size,32,32*32,-1)
        labels = labels.view(batch_size,32,1024)

        loss = criterion(output, labels)


        loss.backward()
        optimizer.step()

        # print("IoU", get_accuracy(loader_train, 100, net))

        # print statistics
        running_loss += loss.data[0]
        if i % step_display == step_display - 1:    # print every 100 mini-batches
            print('TRAINING Epoch: %d %d loss: %.10f' %
                  (epoch + starting_num, i + 1, running_loss/step_display))
            with open('./' + path_save + '/log.txt', 'a') as f:
                f.write('TRAINING Epoch: %d %d loss: %.10f\n' %
                  (epoch + starting_num, i + 1, running_loss/step_display))

            running_loss = 0.0

            acc = get_accuracy(loader_train, 100, net)
            print("IoU: ", acc)
            with open('./' + path_save + '/log.txt', 'a') as f:
                f.write("IoU: "+ str(acc))

    if epoch % step_save == 1:
        torch.save(net.state_dict(), './' + path_save + '/Epoch'+str(epoch+starting_num))

    # net.eval()
    # with open('./' + path_save + '/log.txt', 'a') as f:
    #     accs = get_accuracy(loader_train, 10000, net)
    #     f.write("Epoch: %d Training set: Top-1 %.3f Top-5 %.3f\n" %(epoch + starting_num, accs[0], accs[1]))
    #     print("Epoch:", epoch + starting_num, "Training set: Top-1", accs[0], "Top-5", accs[1])
    #     accs = get_accuracy(loader_val, 10000, net)
    #     print("Epoch:", epoch + starting_num, "Validation set: Top-1",accs[0], "Top-5", accs[1])
    #     f.write("Epoch: %d Validation set: Top-1 %.3f Top-5 %.3f\n" %(epoch + starting_num, accs[0], accs[1]))

print('Finished Training')
