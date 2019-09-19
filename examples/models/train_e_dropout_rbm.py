from torch.utils.data import DataLoader

import torchvision
from recogners.models.e_dropout_rbm import EDropoutRBM

# Creating training and testing dataset
train = torchvision.datasets.MNIST(
    root='./data', train=True, download=True, transform=torchvision.transforms.ToTensor())
test = torchvision.datasets.MNIST(
    root='./data', train=False, download=True, transform=torchvision.transforms.ToTensor())

# Creating training and testing batches
train_batches = DataLoader(train, batch_size=256, shuffle=True, num_workers=1)
test_batches = DataLoader(test, batch_size=10000, shuffle=True, num_workers=1)

# Creating an E-DropoutRBM
model = EDropoutRBM(n_visible=784, n_hidden=256, steps=1,
            learning_rate=0.1, momentum=0, decay=0, temperature=1)

# Training an E-DropoutRBM
error, pl = model.fit(train_batches, epochs=10)

# Reconstructing test set
rec_error, v = model.reconstruct(test_batches)

# Saving model to an output file
model.save('e_dropout_rbm.pkl')

# Checking the model's history
# print(model.history)
