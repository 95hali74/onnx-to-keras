from io import BytesIO
from tempfile import NamedTemporaryFile

import onnx
import torch.nn
from torch.nn import Module
from torchvision import models
from numpy.testing import assert_almost_equal
import numpy as np

from onnx2keras import onnx2keras


def make_onnx_model(net, indata):
    fd = BytesIO()
    torch.onnx.export(net, indata, fd)
    fd.seek(0)
    return onnx.load(fd)


def convert_and_compare_output(net, indata, precition=6, image_out=True, savable=True):
    torch_indata = torch.tensor(indata)
    y1 = net(torch_indata).detach().numpy()
    onnx_model = make_onnx_model(net, torch.zeros_like(torch_indata))
    kernas_net = onnx2keras(onnx_model)
    if savable:
        with NamedTemporaryFile() as f:
            f.close()
            kernas_net.save(f.name)
    y2 = kernas_net.predict(indata.transpose(0, 2, 3, 1))
    if image_out:
        y2 = y2.transpose(0, 3, 1, 2)
    assert_almost_equal(y1, y2, precition)
    return kernas_net

class GlobalAvgPool(Module):
    def forward(self, x):
        return x.mean([2, 3])


class TestOnnx:
    def test_conv(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 16, 7), torch.nn.ReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_conv_no_bias(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 16, 7, bias=False), torch.nn.ReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_conv_padding(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(1, 16, 3, padding=1), torch.nn.ReLU())
        x = np.random.rand(1, 1, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_prelu(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 16, 7), torch.nn.PReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_prelu_per_channel(self):
        act = torch.nn.PReLU(num_parameters=16)
        act.weight[:] = torch.tensor(range(16))
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 16, 7), act)
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x, 5)

    def test_maxpool(self):
        net = torch.nn.Sequential(torch.nn.MaxPool2d(2))
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_concat(self):
        for axis in range(1,4):
            class Dbl(torch.nn.Module):
                def forward(self, x):
                    return torch.cat((x, x), axis)
            x = np.random.rand(1, 3, 224, 224).astype(np.float32)
            convert_and_compare_output(Dbl(), x)

    def test_conv_transpose(self):
        net = torch.nn.Sequential(torch.nn.ConvTranspose2d(3, 16, 5, 2), torch.nn.ReLU())
        x = np.random.rand(1, 3, 112, 112).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_conv_transpose_padding(self):
        net = torch.nn.Sequential(torch.nn.ConvTranspose2d(3, 16, 4, 2, padding=1), torch.nn.ReLU())
        x = np.random.rand(1, 3, 112, 112).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_conv_different_padding(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 64, kernel_size=7, stride=1, padding=(3, 4)))
        x = np.random.rand(1, 3, 384, 544).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_conv_stride2_padding_strange(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3))
        x = np.random.rand(1, 3, 384, 544).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_conv_stride2_padding_simple_odd(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 64, kernel_size=3, stride=2, padding=1))
        x = np.random.rand(1, 3, 223, 223).astype(np.float32)
        kernas_net = convert_and_compare_output(net, x)
        assert [l.__class__.__name__ for l in kernas_net.layers] == ['InputLayer', 'Conv2D']

    def test_conv_stride2_padding_simple_even(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 64, kernel_size=3, stride=2, padding=1))
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        kernas_net = convert_and_compare_output(net, x)
        # assert [l.__class__.__name__ for l in kernas_net.layers] == ['InputLayer', 'Conv2D']

    def test_batchnorm(self):
        bn = torch.nn.BatchNorm2d(3)
        bn.running_mean.uniform_()
        bn.running_var.uniform_()
        net = torch.nn.Sequential(bn, torch.nn.ReLU())
        net.eval()
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_clamp(self):
        class Clamp(Module):
            def forward(self, x):
                return torch.clamp(x, 0.3, 0.7)
        net = torch.nn.Sequential(torch.nn.ReLU(), Clamp(), torch.nn.ReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x, savable=False)

    def test_relu6(self):
        class Clamp(Module):
            def forward(self, x):
                return torch.clamp(x, 0, 6)
        net = torch.nn.Sequential(torch.nn.ReLU(), Clamp(), torch.nn.ReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_depthwise(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 3, 7, groups=3), torch.nn.ReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_depthwise_no_bias(self):
        net = torch.nn.Sequential(torch.nn.Conv2d(3, 3, 7, groups=3, bias=False), torch.nn.ReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_add(self):
        class AddTst(Module):
            def __init__(self):
                Module.__init__(self)
                self.conv1 = torch.nn.Conv2d(3, 3, 7)
                self.conv2 = torch.nn.Conv2d(3, 3, 7)
            def forward(self, x):
                return self.conv1(x).relu_() + self.conv2(x).relu_()
        net = torch.nn.Sequential(AddTst(), torch.nn.ReLU())
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x)

    def test_global_avrage_pooling(self):
        net = torch.nn.Sequential(GlobalAvgPool(), torch.nn.ReLU())
        x = np.random.rand(1, 3, 16, 16).astype(np.float32)
        convert_and_compare_output(net, x, image_out=False)

    def test_dropout(self):
        net = torch.nn.Sequential(GlobalAvgPool(), torch.nn.Dropout(), torch.nn.ReLU())
        net.eval()
        x = np.random.rand(1, 3, 16, 16).astype(np.float32)
        convert_and_compare_output(net, x, image_out=False)

    def test_linear(self):
        net = torch.nn.Sequential(GlobalAvgPool(), torch.nn.Linear(3, 8), torch.nn.ReLU())
        net.eval()
        x = np.random.rand(5, 3, 16, 16).astype(np.float32)
        convert_and_compare_output(net, x, image_out=False)

    def test_mobilenet_v2(self):
        net = models.mobilenet_v2()
        net.eval()
        x = np.random.rand(1, 3, 224, 224).astype(np.float32)
        convert_and_compare_output(net, x, image_out=False)
