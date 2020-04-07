import time

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

import learnergy.utils.exception as e
import learnergy.utils.logging as l
from learnergy.models.rbm import RBM

logger = l.get_logger(__name__)


class DRBM(RBM):
    """A DRBM class provides the basic implementation for Discriminative Bernoulli-Bernoulli Restricted Boltzmann Machines.

    References:
        H. Larochelle and Y. Bengio. Classification using discriminative restricted Boltzmann machines.
        Proceedings of the 25th international conference on Machine learning (2008).

    """

    def __init__(self, n_visible=128, n_hidden=128, n_classes=1, steps=1,
                 learning_rate=0.1, momentum=0, decay=0, temperature=1, use_gpu=False):
        """Initialization method.

        Args:
            n_visible (int): Amount of visible units.
            n_hidden (int): Amount of hidden units.
            n_classes (int): Amount of classes.
            steps (int): Number of Gibbs' sampling steps.
            learning_rate (float): Learning rate.
            momentum (float): Momentum parameter.
            decay (float): Weight decay used for penalization.
            temperature (float): Temperature factor.
            use_gpu (boolean): Whether GPU should be used or not.

        """

        logger.info('Overriding class: RBM -> DRBM.')

        # Override its parent class
        super(DRBM, self).__init__(n_visible, n_hidden, steps, learning_rate,
                                   momentum, decay, temperature, use_gpu)
    
        # Number of classes
        self.n_classes = n_classes 

        # Class weights matrix
        self.U = nn.Parameter(torch.randn(n_classes, n_hidden) * 0.05)

        # Class bias
        self.c = nn.Parameter(torch.zeros(n_classes))

        # Creating the loss function for the DRBM
        self.loss = nn.CrossEntropyLoss()

        # Updating optimizer's parameters with `U`
        self.optimizer.add_param_group({'params': self.U})

        # Updating optimizer's parameters with `c`
        self.optimizer.add_param_group({'params': self.c})

        # Re-checks if current device is CUDA-based due to new parameter
        if self.device == 'cuda':
            # If yes, re-uses CUDA in the whole class
            self.cuda()

        logger.info('Class overrided.')

    @property
    def n_classes(self):
        """int: Number of classes.

        """

        return self._n_classes

    @n_classes.setter
    def n_classes(self, n_classes):
        if not isinstance(n_classes, int):
            raise e.TypeError('`n_classes` should be an integer')
        if n_classes <= 0:
            raise e.ValueError('`n_classes` should be > 0')

        self._n_classes = n_classes

    @property
    def U(self):
        """torch.nn.Parameter: Class weights' matrix.

        """

        return self._U

    @U.setter
    def U(self, U):
        if not isinstance(U, nn.Parameter):
            raise e.TypeError('`U` should be a PyTorch parameter')

        self._U = U

    @property
    def c(self):
        """torch.nn.Parameter: Class units bias.

        """

        return self._c

    @c.setter
    def c(self, c):
        if not isinstance(c, nn.Parameter):
            raise e.TypeError('`c` should be a PyTorch parameter')

        self._c = c

    @property
    def loss(self):
        """torch.nn.CrossEntropyLoss: Cross-Entropy loss function.

        """

        return self._loss

    @loss.setter
    def loss(self, loss):
        if not isinstance(loss, nn.CrossEntropyLoss):
            raise e.TypeError('`loss` should be a CrossEntropy')

        self._loss = loss

    def labels_sampling(self, samples):
        """Calculates labels probabilities by samplings, i.e., P(y|v).

        Args:
            samples (torch.Tensor): Samples to be labels-calculated.

        Returns:
            Labels' probabilities based on input samples.

        """

        # Creating an empty tensor for holding the probabilities per class
        probs = torch.zeros(samples.size(0), self.n_classes)

        # Creating an empty tensor for holding the probabilities considering all classes
        probs_sum = torch.zeros(samples.size(0))

        # Calculate samples' activations
        activations = F.linear(samples, self.W.t(), self.b)

        # Creating a Softplus function for numerical stability
        s = nn.Softplus()

        # Iterating through every possible class
        for i in range(self.n_classes):
            # Calculates the probability for the particular class
            probs[:, i] = torch.exp(self.c[i]) + torch.sum(s(activations + self.U[i, :]), dim=1)

        # Calculates the probability over all classes
        probs_sum = torch.exp(torch.sum(self.c)) + torch.sum(s(activations + torch.sum(self.U)), dim=1)

        # Finally, calculates P(y|v)
        probs = torch.div(probs, probs_sum.unsqueeze(1))

        # Recovering the predictions based on the probabilities
        preds = torch.argmax(probs.detach(), 1)

        return probs, preds

    def fit(self, dataset, batch_size=128, epochs=10):
        """Fits a new DRBM model.

        Args:
            dataset (torch.utils.data.Dataset): A Dataset object containing the training data.
            batch_size (int): Amount of samples per batch.
            epochs (int): Number of training epochs.

        Returns:
            Loss and accuracy from the training step.

        """

        # Transforming the dataset into training batches
        batches = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=1)

        # For every epoch
        for e in range(epochs):
            logger.info(f'Epoch {e+1}/{epochs}')

            # Calculating the time of the epoch's starting
            start = time.time()

            # Resetting epoch's MSE and pseudo-likelihood to zero
            loss = 0
            acc = 0

            # For every batch
            for samples, labels in batches:
                # Flattening the samples' batch
                samples = samples.view(len(samples), self.n_visible)

                # Checking whether GPU is avaliable and if it should be used
                if self.device == 'cuda':
                    # Applies the GPU usage to the data
                    samples = samples.cuda()

                # Calculates labels probabilities and predictions by sampling
                probs, preds = self.labels_sampling(samples)

                # Calculates the loss for further gradients' computation
                cost = self.loss(probs, labels)

                # Initializing the gradient
                self.optimizer.zero_grad()

                # Computing the gradients
                cost.backward()

                # Updating the parameters
                self.optimizer.step()

                # Gathering the size of the batch
                batch_size = samples.size(0)

                # Calculating current's batch accuracy
                batch_acc = torch.mean((torch.sum(preds == labels).float()) / batch_size)

                # Summing up to epochs' loss and accuracy
                loss += cost
                acc += batch_acc

            # Normalizing the loss and accuracy with the number of batches
            loss /= len(batches)
            acc /= len(batches)

            # Calculating the time of the epoch's ending
            end = time.time()

            # Dumps the desired variables to the model's history
            self.dump(loss=loss.item(), acc=acc.item(), time=end-start)

            logger.info(f'Loss: {loss} | Accuracy: {acc}')

        return loss, acc

    def predict(self, dataset):
        """Predicts batches of new samples.

        Args:
            dataset (torch.utils.data.Dataset): A Dataset object containing the testing data.

        Returns:
            Prediction probabilities and labels, i.e., P(y|v).

        """

        logger.info(f'Predicting new samples ...')

        # Resetting accuracy to zero
        acc = 0

        # Defining the batch size as the amount of samples in the dataset
        batch_size = len(dataset)

        # Transforming the dataset into training batches
        batches = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=1)

        # For every batch
        for samples, labels in batches:
            # Flattening the samples' batch
            samples = samples.view(len(samples), self.n_visible)

            # Checking whether GPU is avaliable and if it should be used
            if self.device == 'cuda':
                # Applies the GPU usage to the data
                samples = samples.cuda()

            # Calculating labels probabilities and predictions by sampling
            probs, preds = self.labels_sampling(samples)

            # Calculating current's batch accuracy
            batch_acc = torch.mean((torch.sum(preds == labels).float()) / batch_size)

            # Summing up the prediction accuracy
            acc += batch_acc

        # Normalizing the accuracy with the number of batches
        acc /= len(batches)

        logger.info(f'Accuracy: {acc}')

        return acc, probs, preds