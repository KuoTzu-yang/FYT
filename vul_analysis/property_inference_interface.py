import math, copy
import numpy as np

import torch
import torchvision
import torchvision.transforms as transforms
import torch.optim as optim
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable

# from binary_MNIST_models import NaiveC, NormalC, CNN
from MNIST_models import NaiveC, NormalC, CNN, robustified_FC, robustified_CNN
from dataset_utils import *
from LP_utils import *

class PropertyInferenceInterface():

    def __init__(self, meta_params):
        # Load meat parameters
        self.meta_params = meta_params

        # Initialization 
        MNIST_train_dataset = torchvision.datasets.MNIST(root='./data', transform=transforms.ToTensor(), train=True, download=True)
        MNIST_test_dataset = torchvision.datasets.MNIST(root='./data', transform=transforms.ToTensor(), train=False, download=True)
        self.train_loader = torch.utils.data.DataLoader(dataset=MNIST_train_dataset, batch_size=50000, shuffle=False)
        self.test_loader = torch.utils.data.DataLoader(dataset=MNIST_test_dataset, batch_size=10000, shuffle=False)
        self.train_dataset = None
        self.test_dataset = None

        self.model = None
        self.retrained_model = None 
        self.twisted_model = None 
        self.dropout_rate = None

        self.LPs_set = None        
        self.differentation_lines = None 

        # Prepare dataset 
        self._create_train_dataset()
        self._create_test_dataset()

    def _create_train_dataset(self):
        X, Y = None, None 
        
        for (samples, labels) in self.train_loader:
            if self.meta_params['flatten'] is True:
                X = samples.reshape(-1, 784).numpy()
            else:
                X = samples.numpy()
            Y = (labels.numpy())
        
            # Prepare subset 
            if 'size_of_train_set' in list(self.meta_params.keys()):
                (X, Y) = extract_subset(X, Y, self.meta_params['size_of_train_set'])
            break
        
        self.train_dataset = (X, Y)

    def _create_test_dataset(self):
        X, Y = None, None 

        for (samples, labels) in self.test_loader:
            if self.meta_params['flatten'] is True:
                X = samples.reshape(-1, 784).numpy()
            else:
                X = samples.numpy()
            Y = (labels.numpy())
        
            # Prepare subset 
            if 'size_of_test_set' in list(self.meta_params.keys()):
                (X, Y) = extract_subset(X, Y, self.meta_params['size_of_test_set'])
            break
        
        self.test_dataset = (X, Y)

    def store_model(self, model_name):
        torch.save(self.model, model_name)

    def load_model(self, model_name):
        self.model = torch.load(model_name)

    def set_dropout_rate(self, dropout_rate):
        self.dropout_rate = dropout_rate

    def generate_model(self, num_of_epochs=15):
        model_type = self.meta_params['model_type']
        if model_type == 'naive':
            model = NaiveC()
        elif model_type == 'normal':
            model = NormalC()
        elif model_type == 'CNN':
            model = CNN()

        X, Y = self.train_dataset
        
        model.train()

        # Training
        loss_func, optimizer = nn.CrossEntropyLoss(), torch.optim.Adam(model.parameters(), lr=1e-3)
        for epoch in range(num_of_epochs):
            print('Generate', model_type, 'model, epoch', epoch, '...')
            for idx, data in enumerate(X):
                # Transform from numpy to torch & correct the shape (expand dimension) and type (float32 and int64)
                data = torch.from_numpy(np.expand_dims(data, axis=0).astype(np.float32))
                label = torch.from_numpy(np.array([Y[idx]]).astype(np.int64))
        
                # Forwarding
                prediction = model.forward(data)
                loss = loss_func(prediction, label)

                # Optimization (back-propogation)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        
        self.model = model

    def generate_retrained_model(self, model_type, num_of_epochs=15):
        ''' 
        - Change the architecture & Retrain a new model from scratches 
        '''
        X, Y = self.train_dataset
        if model_type == 'FC':
            model = robustified_FC(self.dropout_rate)
        elif model_type == 'CNN':
            model = robustified_CNN(self.dropout_rate)
        else: 
            pass 

        model.train()

        # Training
        loss_func, optimizer = nn.CrossEntropyLoss(), torch.optim.Adam(model.parameters(), lr=1e-3)
        for epoch in range(num_of_epochs):
            print('Generate retrained', model_type, 'model, epoch', epoch, '...')
            for idx, data in enumerate(X):
                # Transform from numpy to torch & correct the shape (expand dimension) and type (float32 and int64)
                data = torch.from_numpy(np.expand_dims(data, axis=0).astype(np.float32))
                label = torch.from_numpy(np.array([Y[idx]]).astype(np.int64))
        
                # Forwarding
                prediction = model.forward(data)
                loss = loss_func(prediction, label)

                # Optimization (back-propogation)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        
        self.retrained_model = model

    def generate_twisted_model(self, model_type, num_of_epochs=15):
        ''' 
        - Currently,CNN only (FC should be added in the future) 
        - Add a dropout layer & Fine-tune weights  
        '''

        # Create an untrained robustified CNN
        twisted_model = robustified_CNN(self.dropout_rate)
        original_model = copy.deepcopy(self.model)
        original_model.train()
        twisted_model.train()

        # Load the original model 
        original_state = original_model.state_dict()
        for name, param in twisted_model.state_dict().items():
            if name not in original_state:
                print('Not in original_state:', name)
                continue
            
            param.copy_(original_state[name])

        # Retraining 
        X, Y = self.train_dataset
        loss_func, optimizer = nn.CrossEntropyLoss(), torch.optim.Adam(twisted_model.parameters(), lr=1e-3)
        for epoch in range(num_of_epochs):
            print('Generate twisted', model_type, 'model, epoch', epoch, '...')
            for idx, data in enumerate(X):
                # Transform from numpy to torch & correct the shape (expand dimension) and type (float32 and int64)
                data = torch.from_numpy(np.expand_dims(data, axis=0).astype(np.float32))
                label = torch.from_numpy(np.array([Y[idx]]).astype(np.int64))
        
                # Forwarding
                prediction = twisted_model.forward(data)
                loss = loss_func(prediction, label)

                # Optimization (back-propogation)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        self.twisted_model = twisted_model

    def eval_model(self, dataset_type, on_retrained_model=False, on_twisted_model=False):
        assert not (on_twisted_model and on_retrained_model)

        if dataset_type == 'train':
            X, Y = self.train_dataset
        else: 
            X, Y = self.test_dataset

        if on_retrained_model:
            model = copy.deepcopy(self.retrained_model)
        elif on_twisted_model:
            model = copy.deepcopy(self.twisted_model)
        else:
            model = copy.deepcopy(self.model)

        model.eval() # unsure 
        datas = torch.from_numpy(X.astype(np.float32))
        labels = torch.from_numpy(Y.astype(np.int64))
        
        # Forwarding
        outputs = model.forward(datas).detach().numpy()
        predictions = np.argmax(outputs, axis=1)

        total = labels.shape[0]
        correct = (predictions == labels.numpy()).sum().item()
        acc = correct/total
            
        return acc

    def generate_signatures(self, is_benign=True, type_of_attack=None, num_of_signatures=None, eps=0.5):
        X, Y = self.train_dataset
        model = copy.deepcopy(self.model)

        if not is_benign: 
            import attacker
            if type_of_attack == 'i_FGSM':
                A = attacker.iterative_FGSM_attacker()
            elif type_of_attack == 'JSMA':
                A = attacker.JSMA_attacker()
            elif type_of_attack == 'CW_L2':
                A = attacker.CW_L2_attacker()
            else:
                A = NotImplemented

        model.eval()
        set_of_signatures = []

        if not (num_of_signatures is None): X, Y = X[:num_of_signatures], Y[:num_of_signatures]

        for i in range(len(X)):
            print(i)
            x, y = X[i], Y[i]

            if not is_benign:
                adv_x, is_att_success = A.create_adv_input(x, y, model, eps)
                if is_att_success: 
                    adv_x = (adv_x.detach().numpy())[0]
                    singatures = extract_signature_from_CNN(model, adv_x)
                else:
                    continue 
            else:
                singatures = extract_signature_from_CNN(model, x) 
            set_of_signatures.append(singatures)

        return set_of_signatures

    def generate_LPs(self, on_retrained_model=False, on_twisted_model=False):
        ''' 
        - Generate the provanence set for each output class
        '''
        X, Y = self.train_dataset
        
        if on_retrained_model:
            model = copy.deepcopy(self.retrained_model)
        elif on_twisted_model:
            model = copy.deepcopy(self.twisted_model)
        else:
            model = copy.deepcopy(self.model)
        model.eval()
        model_type = self.meta_params['model_type']

        NUM_MNIST_CLASSES = 10 # should be further adjusted 
        num_output_classes = NUM_MNIST_CLASSES

        # Initialize LPs_set 
        LPs_set = []
        for i in range(num_output_classes):
            LPs_set.append([])
        for i in range(num_output_classes):
            for _ in range(self.meta_params['num_of_LPs']):
                LPs_set[i].append([])
            
        # Extract and store LP(s)
        for i in range(len(X)):
            x, y = X[i], Y[i]
            LPs = extract_all_LP(model, model_type, x, self.dropout_rate) 
            for i in range(len(LPs)):
                (LPs_set[y])[i].append(LPs[i])

        self.LPs_set = LPs_set

    def property_match(self, x, y, on_retrained_model, on_twisted_model, verbose=True):
        ''' 
        - Given a sample and its classified outcome, (x, y)
        - We compare provanence of x (p) to the provanence set of y (P)
        - Then, we compute the risk score & decide whether a given sample, x, is 'benign' or 'adversarial' 
        '''
        # Get the provanence set according to the output class y = model(x)
        PS = self.LPs_set[y]

        # Get the provanence of x 
        if on_retrained_model:
            model = copy.deepcopy(self.retrained_model)
        elif on_twisted_model:
            model = copy.deepcopy(self.twisted_model)
        else:
            model = copy.deepcopy(self.model)
        model.eval()
        model_type = self.meta_params['model_type']
        ps = extract_all_LP(model, model_type, x, self.dropout_rate) 

        # Create intermediate values 
        LP_status, LP_risk_score, is_benign = [], [], None
        differentation_lines = self.differentation_lines

        # Case 1: self.differentation_lines is None 
        # -> compute risk_score only 
        if (differentation_lines is None): 
            for i in range(len(PS)):
                P, p = np.array(PS[i]), np.array(ps[i])
                prob_P = np.sum(P, axis=0)/(P.shape[0])
                abs_diff = np.absolute(prob_P-p)
                risk_score = np.sum(abs_diff)
                LP_risk_score.append(risk_score)
        # Case 2: self.differentation_lines exists
        # -> compute risk_score and status (by comparing to differentation_lines)
        else:     
            for i in range(len(PS)):
                P, p, differentation_line = np.array(PS[i]), np.array(ps[i]), differentation_lines[i]

                # Compute score (the method to compute score can be further adjusted)
                prob_P = np.sum(P, axis=0)/(P.shape[0])
                abs_diff = np.absolute(prob_P-p)
                risk_score = np.sum(abs_diff)

                # If score is lower than differentiation line, then it's 'benign'. 
                # Otherwise, it's 'adversarial'.
                status = 'benign' if risk_score < differentation_line else 'adversarial'
                LP_status.append(status)
                LP_risk_score.append(risk_score)

            # Decide whether a given sample x is 'benign' or 'adversarial'
            # -> the benign_condition should be further adjusted 
            benign_condition = ('benign' == LP_status[0] and 'benign' == LP_status[1] and 'benign' == LP_status[2])
            is_benign = True if benign_condition else False  

        return (is_benign, LP_status, LP_risk_score)

    def evaluate_algorithm_on_test_set(self, verbose=True, on_retrained_model=False, on_twisted_model=False):
        assert not (on_twisted_model and on_retrained_model)

        self._set_differentation_lines(95, on_retrained_model, on_twisted_model)
        B_num_count, B_correct_count, B_valid_count, B_LPs, B_LPs_score = self._evaluate_benign_samples(verbose, on_retrained_model, on_twisted_model)
        A_num_count, A_correct_count, A_success_count, A_AA_count, A_BB_count, A_LPs, A_LPs_score = self._evaluate_adversarial_samples(verbose, on_retrained_model, on_twisted_model)
        A_non_success_count = A_correct_count - A_success_count

        B_accuracy, B_TNR = B_correct_count/B_num_count, B_valid_count/B_correct_count 
        A_accuracy, A_ASR = A_correct_count/A_num_count, A_success_count/A_correct_count
        A_TNR = None if A_non_success_count == 0 else A_BB_count/A_non_success_count
        A_TPR = None if A_success_count == 0 else A_AA_count/A_success_count

        # assert A_accuracy == B_accuracy
        return (B_accuracy, B_TNR), (A_accuracy, A_ASR, A_TNR, A_TPR), (B_LPs, A_LPs), (B_LPs_score, A_LPs_score)

    def _set_differentation_lines(self, qr, on_retrained_model, on_twisted_model):
        ''' Private function
        - Set the differentiation lines according to training dataset,
        - Apply differentation lines on B (normal test samples) and A (adversarial test samples)
        '''

        # Load (train) dataset and model 
        X, Y = self.train_dataset 
        model = (self.model).eval()

        # Create intermediate variables 
        LPs_score = []

        for i in range(len(X)):
            x, y = X[i], Y[i]
            
            # Filter out samples can not be correctly classified by the given model 
            output = model.forward(torch.from_numpy(np.expand_dims(x, axis=0).astype(np.float32)))
            y_ = (output.max(1, keepdim=True)[1]).item() 
            if y_ != y:
                continue

            # Collect LP_risk_score among train dataset 
            _, _, LP_risk_score = self.property_match(x, y_, on_retrained_model, on_twisted_model, verbose=False) 
            LPs_score.append(LP_risk_score)

        # Compute differentation lines 
        LPs_score = np.array(LPs_score)
        differentation_lines = []
        for i in range(LPs_score.shape[1]):
            LP_score = LPs_score[:,i]
            differentation_lines.append(np.percentile(LP_score, qr))

        # Store in PI
        self.differentation_lines = differentation_lines

    def _evaluate_benign_samples(self, verbose, on_retrained_model, on_twisted_model):
        ''' Private function 
        - Samples are extracted from the test dataset
        total_count   : # of samples extracted from dataset
        correct_count : # of samples (classified correctly)
        valid_count   : # of samples (classified correctly & classified as benign)
        '''

        # Load (test) dataset and model 
        X, Y = self.test_dataset

        if on_retrained_model:
            model = copy.deepcopy(self.retrained_model).eval()
        elif on_twisted_model:
            model = copy.deepcopy(self.twisted_model).eval()
        else:
            model = copy.deepcopy(self.model).eval()

        # Create intermediate variables 
        num_count, correct_count, valid_count = len(X), len(X), 0
        LPs, LPs_score = [], []

        for i in range(correct_count):
            if self.meta_params['is_debug']:
                print('Evaluate', i, 'th benign sample ...')

            x, y = X[i], Y[i]
            
            # Filter out samples can not be correctly classified by the given model 
            output = model.forward(torch.from_numpy(np.expand_dims(x, axis=0).astype(np.float32)))
            y_ = (output.max(1, keepdim=True)[1]).item() 
            if y_ != y:
                correct_count -= 1
                continue

            # Generate experimental result 
            is_benign, LP_status, LP_risk_score = self.property_match(x, y_, on_retrained_model, on_twisted_model, verbose) 

            # Record experimental info 
            LPs.append(LP_status)
            LPs_score.append(LP_risk_score)
            valid_count += 1 if is_benign else 0 

        if verbose:
            NUM_OF_CHAR_INDENT = 50 
            print('Evaluate on benign samples with test set')
            print('# of samples'.ljust(NUM_OF_CHAR_INDENT), ':', num_count)
            # print('# of correctly classified samples'.ljust(NUM_OF_CHAR_INDENT), ':', correct_count)
            # print('# of correctly classified samples')
            # print('     which are indentified as "benign"'.ljust(NUM_OF_CHAR_INDENT), ':', valid_count)
            # print()
            print('Accuracy'.ljust(NUM_OF_CHAR_INDENT), ':', round((correct_count/num_count), 3), '(', correct_count, '/', num_count, ')')
            print('True Negative Rate, TNR (B -> B)'.ljust(NUM_OF_CHAR_INDENT), ':', round((valid_count/correct_count), 3), '(', valid_count, '/', correct_count, ')')
            print()

        return num_count, correct_count, valid_count, LPs, LPs_score

    def _evaluate_adversarial_samples(self, verbose, on_retrained_model, on_twisted_model):
        ''' Private function 
        - Samples are extracted from the test dataset
        total_count   : # of samples extracted from dataset
        correct_count : # of samples (classified correctly)
        '''

        # Create attack for generating adversarial samples         
        import attacker
        if self.meta_params['adv_attack'] == 'i_FGSM':
            A = attacker.iterative_FGSM_attacker()
        elif self.meta_params['adv_attack'] == 'JSMA':
            A = attacker.JSMA_attacker()
        elif self.meta_params['adv_attack'] == 'CW_L2':
            A = attacker.CW_L2_attacker()
        else:
            A = NotImplemented

        # Load (test) dataset and model 
        X, Y = self.test_dataset
        if on_retrained_model:
            model = copy.deepcopy(self.retrained_model).eval()
        elif on_twisted_model:
            model = copy.deepcopy(self.twisted_model).eval()
        else:
            model = copy.deepcopy(self.model).eval()

        # Create intermediate variables 
        LPs, LPs_score = [], []
        num_count, correct_count = len(X), len(X)
        success_count, non_success_count = 0, 0
        BB_count, BA_count, AA_count, AB_count = 0, 0, 0, 0

        for i in range(correct_count):
            iterative = False 
            if iterative: eps, eps_incre_unit, eps_upper_bound = 0, 0.01, 1 # if iterative 
            else: eps = 0.25 # if not iterative 

            # Debug information 
            if self.meta_params['is_debug']:
                print('Evaluate', i, 'th adversarial sample via', self.meta_params['adv_attack'], '...')

            x, y = X[i], Y[i]
            adv_x, adv_y = None, None 

            # Filter out samples can not be correctly classified by the given model 
            output = model.forward(torch.from_numpy(np.expand_dims(x, axis=0).astype(np.float32)))
            y_ = (output.max(1, keepdim=True)[1]).item() 
            if y_ != y:
                correct_count -= 1
                continue

            # Iterative attack process start, slightly increase eps until larger than the upper bound 
            if iterative:
                is_attack_successful = False
                while (not is_attack_successful):
                    eps += eps_incre_unit
                    if eps > eps_upper_bound:
                        break  

                    adv_x, is_att_success = A.create_adv_input(x, y, model, eps)
                    if is_att_success:
                        is_attack_successful = True
                        adv_x = (adv_x.detach().numpy())[0]
            else:
                adv_x, is_attack_successful = A.create_adv_input(x, y, model, eps)
                adv_x = (adv_x.detach().numpy())[0]

            # Debug information 
            if is_attack_successful:
                adv_x_ = np.expand_dims(adv_x, axis=0).astype(np.float32)
                adv_x_ = torch.from_numpy(adv_x_)
                output_ = model.forward(adv_x_)
                adv_y = (output_.max(1, keepdim=True)[1]).item()
                is_benign, LP_status, LP_risk_score = self.property_match(adv_x, adv_y, on_retrained_model, on_twisted_model, verbose) 
            else:
                is_benign, LP_status, LP_risk_score = self.property_match(x, y_, on_retrained_model, on_twisted_model, verbose) 

            # LPs.append(LP_status)
            # LPs_score.append(LP_risk_score)

            # B 
            if (not is_attack_successful):
                non_success_count += 1
                BB_count += 1 if is_benign else 0 
                BA_count += 1 if (not is_benign) else 0
            # A
            else: 
                success_count += 1
                AB_count += 1 if is_benign else 0
                AA_count += 1 if (not is_benign) else 0

                # expExp: current we only record information from succesfully attacked samples 
                LPs.append(LP_status)
                LPs_score.append(LP_risk_score)

        # Record AST 
        assert (success_count+non_success_count)==correct_count
        AST = success_count/correct_count

        if verbose:
            NUM_OF_CHAR_INDENT = 50 
            print('Evaluate on adversarial samples with test set')
            # print('# of samples'.ljust(NUM_OF_CHAR_INDENT), ':', num_count)
            # print('# of correctly classified samples'.ljust(NUM_OF_CHAR_INDENT), ':', correct_count)
            # print('# of correctly classified samples')
            # print('which are NOT succesfully attacked -> "benign"'.ljust(NUM_OF_CHAR_INDENT), ':', non_success_count)
            # print('B -> B count'.ljust(NUM_OF_CHAR_INDENT), ':', BB_count)
            # print('B -> A count'.ljust(NUM_OF_CHAR_INDENT), ':', BA_count)
            if not (non_success_count == 0): 
                print('True Negative Rate, TNR (B -> B)'.ljust(NUM_OF_CHAR_INDENT), ':', round((BB_count/non_success_count), 3), '(', BB_count, '/', non_success_count, ')')

            # print()
            # print('# of correctly classified samples')
            # print('which are succesfully attacked -> "adversarial"'.ljust(NUM_OF_CHAR_INDENT), ':', success_count)
            # print('A -> B count'.ljust(NUM_OF_CHAR_INDENT), ':', AB_count)
            # print('A -> A count'.ljust(NUM_OF_CHAR_INDENT), ':', AA_count)
            if not (success_count == 0): 
                print('True Positive Rate, TPR (A -> A)'.ljust(NUM_OF_CHAR_INDENT), ':', round((AA_count/success_count), 3), '(', AA_count, '/', success_count, ')')

            # print()
            print('Attack success rate'.ljust(NUM_OF_CHAR_INDENT), ':', round(AST, 3), '(', success_count, '/', correct_count, ')')

        return num_count, correct_count, success_count, AA_count, BB_count, LPs, LPs_score
