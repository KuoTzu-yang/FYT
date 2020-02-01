import torch 
import torch.nn as nn
import torch.nn.functional as F

import numpy as np

import copy
import random

class CNN(nn.Module):

    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 16, kernel_size=5)
        self.conv2 = nn.Conv2d(16, 16, kernel_size=5)
        self.conv3 = nn.Conv2d(16, 32, kernel_size=5)
        self.fc1 = nn.Linear(3*3*32, 64)
        self.fc2 = nn.Linear(64, 10)

    def forward(self, x):
        x = F.relu(self.conv1(x)) # (24, 24, 16)
        x = F.relu(F.max_pool2d(self.conv2(x), 2)) # (20, 20, 16) -> (10, 10, 16)
        x = F.relu(F.max_pool2d(self.conv3(x), 2)) # (6, 6, 32) -> (3, 3, 32)
        x = x.view(-1, 3*3*32)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)

class Guard(nn.Module):
    def __init__(self):
        super().__init__()
        self.relu = nn.ReLU()
        
        self.kernel_size = 1
        
        self.pre_l1_conv1 = nn.Conv2d(16, 8, 1)
        self.pre_l2_conv1 = nn.Conv2d(16, 8, 1)
        self.pre_l3_conv1 = nn.Conv2d(32, 8, 1)
        
        self.xh1 = nn.Conv2d(8, 8, 1)
        self.xh2 = nn.Conv2d(8, 8, 1)
        self.xh3 = nn.Conv2d(8, 8, 1)
        self.xh4 = nn.Linear(64, 64)
        
        self.hh12 = nn.Conv2d(8, 8, 15)
        self.hh23 = nn.Conv2d(8, 8, 8)
        self.hh34 = nn.Linear(8*3*3, 64)
        
        self.hy = nn.Linear(64, 2)

    def forward(self, f1, f2, f3, f4):
        x1 = self.relu(self.pre_l1_conv1(f1)) # 1, 8, 24, 24 
        x2 = self.relu(self.pre_l2_conv1(f2)) # 1, 8, 10, 10
        x3 = self.relu(self.pre_l3_conv1(f3)) # 1, 8, 3, 3
        x4 = f4.view(-1, 64) # 1, 64
        
        h1 = self.relu(self.xh1(x1))
        h1 = F.dropout2d(h1, p=0.1)
        h2 = self.relu(torch.add(self.hh12(h1), self.xh2(x2)))
        h2 = F.dropout2d(h2, p=0.1)
        h3 = self.relu(torch.add(self.hh23(h2), self.xh3(x3)))
        h3 = F.dropout2d(h3, p=0.1)
        h3 = h3.view(-1, 8*3*3)
        h4 = self.relu(torch.add(self.hh34(h3), self.xh4(x4)))
        h4 = F.dropout(h4, p=0.1)
        outputs = self.hy(h4)
        return outputs
    
def store_model(model, model_name):
    torch.save(model, model_name)

def load_model(model_name):
    return torch.load(model_name)

def train(train_dataset, model, loss_func, opt, num_of_epochs):
    model.train()
    X, Y = train_dataset

    for epoch in range(num_of_epochs):
        print('Generate CNN model, epoch:', epoch+1, '...')
        for idx, data in enumerate(X):
            # Transform from numpy to torch & correct the shape (expand dimension) and type (float32 and int64)
            data = torch.from_numpy(np.expand_dims(data, axis=0).astype(np.float32))
            label = torch.from_numpy(np.array([Y[idx]]).astype(np.int64))

            # Forwarding
            prediction = model.forward(data)
            loss = loss_func(prediction, label)

            # Optimization (back-propogation)
            if random.random() < 0.6:
                opt.zero_grad()
                loss.backward()
                opt.step()

        print('acc:', eval_model(model, train_dataset))

    return model

def eval_model(model, dataset):
    X, Y = dataset
    datas = torch.from_numpy(X.astype(np.float32))
    labels = torch.from_numpy(Y.astype(np.int64))

    # Forwarding
    outputs = model.forward(datas).detach().numpy()
    predictions = np.argmax(outputs, axis=1)

    total = labels.shape[0]
    correct = (predictions == labels.numpy()).sum().item()
    acc = correct/total

    return acc

def preprocess(x):
    f1 = torch.from_numpy(np.array(x[0])).float()
    f2 = torch.from_numpy(np.array(x[1])).float()
    f3 = torch.from_numpy(np.array(x[2])).float()
    f4 = np.expand_dims(x[3], axis=2)
    f4 = torch.from_numpy(f4).float()
    return f1, f2, f3, f4
        

def train_guard_model(guard_model, set_of_train_dataset, set_of_test_dataset, adv_types, epoches):
    loss_func, optimizer = nn.BCEWithLogitsLoss(), torch.optim.Adam(guard_model.parameters())
    train_accs, test_accs, losses = [], [], []
    set_train_sub_accs, set_test_sub_accs = [], []

    for epoch in range(epoches):
        total_loss = None 
        # labeling ...
        train_dataset, train_labels = [], []
        for dataset, adv_type in zip(set_of_train_dataset, adv_types):
            for singatures in dataset:
                train_dataset.append(singatures)
                if adv_type == 'None': label = torch.from_numpy(np.array([[1, 0]])).float()
                else: label = torch.from_numpy(np.array([[0, 1]])).float()
                train_labels.append(label)
  
        # shuffling 
        shuffle_indexs = np.arange(len(train_dataset))
        np.random.shuffle(shuffle_indexs)

        # training 
        for index in shuffle_indexs:
            singatures, label = train_dataset[index], train_labels[index]
            f1, f2, f3, f4 = preprocess(singatures)
            outputs = guard_model.forward(f1, f2, f3, f4)

            # for recording the training process 
            loss = loss_func(outputs, label)
            if total_loss is None: total_loss = loss 
            else: total_loss += loss
            
            # Optimization (back-propogation)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
        train_acc, train_sub_accs = test_guard_model(guard_model, set_of_train_dataset, adv_types, verbose=False)
        print()
        test_acc, test_sub_accs = test_guard_model(guard_model, set_of_test_dataset, adv_types, verbose=False)
        print()
        print('epoch:', (epoch+1), 'loss:', total_loss.item())    
        print('acc (train):', train_acc)
        print('acc (test):', test_acc)
        print()
        train_accs.append(train_acc)
        test_accs.append(test_acc)
        set_train_sub_accs.append(train_sub_accs)
        set_test_sub_accs.append(test_sub_accs)
        losses.append(total_loss)
        
    return train_accs, test_accs, losses, set_train_sub_accs, set_test_sub_accs

def test_guard_model(guard_model, set_of_test_dataset, adv_types, verbose=True):
    total_train_correct_count, total_train_count = 0, 0 
    sub_accs = []
    for test_dataset, adv_type in zip(set_of_test_dataset, adv_types):
        current_count = 0
        for singatures in test_dataset:
            f1, f2, f3, f4 = preprocess(singatures)
            outputs = guard_model.forward(f1, f2, f3, f4)
            if adv_type == 'None': label = torch.from_numpy(np.array([[1, 0]])).float()
            else: label = torch.from_numpy(np.array([[0, 1]])).float()

            prediction = (outputs.max(1, keepdim=True)[1]).item()     
            if adv_type == 'None': 
                if (prediction == 0): 
                    current_count += 1
            else: 
                if (prediction == 1): 
                    current_count += 1
            
        # record the current train set acc
        if verbose: 
            if adv_type == 'None': 
                print('benign correct:', current_count, '/', len(test_dataset))
            else:
                print('adv (', adv_type, ') correct:', current_count, '/', len(test_dataset))

        sub_accs.append(current_count/len(test_dataset))
        total_train_correct_count += current_count
        total_train_count += len(test_dataset)

    acc = total_train_correct_count/total_train_count
    if verbose: 
        print('acc:', acc)

    return acc, sub_accs