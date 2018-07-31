#! /usr/bin/python
# -*- coding: utf-8 -*-

import tensorflow as tf

from tensorlayer.layers.core import Layer
from tensorlayer.layers.core import LayersConfig

from tensorlayer.layers.utils import quantize_active_overflow
from tensorlayer.layers.utils import quantize_weight_overflow

from tensorlayer import logging

from tensorlayer.decorators import deprecated_alias

__all__ = ['QuantizedConv2d']


class QuantizedConv2d(Layer):
    """The :class:`QuantizedConv2dWithBN` class is a quantized convolutional layer with BN, which weights are 'bitW' bits and the output of the previous layer
    are 'bitA' bits while inferencing.
    Note that, the bias vector would not be binarized.

    Parameters
    ----------
    prev_layer : :class:`Layer`
        Previous layer.
    bitW : int
        The bits of this layer's parameter
    bitA : int
        The bits of the output of previous layer
    n_filter : int
        The number of filters.
    filter_size : tuple of int
        The filter size (height, width).
    strides : tuple of int
        The sliding window strides of corresponding input dimensions.
        It must be in the same order as the ``shape`` parameter.
    padding : str
        The padding algorithm type: "SAME" or "VALID".
    act : activation function
        The activation function of this layer.
    bitW : int
        The bits of this layer's parameter
    bitA : int
        The bits of the output of previous layer
    use_gemm : boolean
        If True, use gemm instead of ``tf.matmul`` for inferencing. (TODO).
    W_init : initializer
        The initializer for the the weight matrix.
    b_init : initializer or None
        The initializer for the the bias vector. If None, skip biases.
    W_init_args : dictionary
        The arguments for the weight matrix initializer.
    b_init_args : dictionary
        The arguments for the bias vector initializer.
    use_cudnn_on_gpu : bool
        Default is False.
    data_format : str
        "NHWC" or "NCHW", default is "NHWC".
    name : str
        A unique layer name.

    Examples
    ---------
    >>> import tensorflow as tf
    >>> import tensorlayer as tl
    >>> x = tf.placeholder(tf.float32, [None, 256, 256, 3])
    >>> net = tl.layers.InputLayer(x, name='input')
    >>> net = tl.layers.QuantizedConv2d(net, 32, (5, 5), (1, 1), padding='SAME', act=tf.nn.relu, name='qcnn1')
    >>> net = tl.layers.MaxPool2d(net, (2, 2), (2, 2), padding='SAME', name='pool1')
    >>> net = tl.layers.BatchNormLayer(net, act=tl.act.htanh, is_train=True, name='bn1')
    ...
    >>> net = tl.layers.QuantizedConv2d(net, 64, (5, 5), (1, 1), padding='SAME', act=tf.nn.relu, name='qcnn2')
    >>> net = tl.layers.MaxPool2d(net, (2, 2), (2, 2), padding='SAME', name='pool2')
    >>> net = tl.layers.BatchNormLayer(net, act=tl.act.htanh, is_train=True, name='bn2')

    """

    @deprecated_alias(layer='prev_layer', end_support_version=1.9)  # TODO remove this line for the 1.9 release
    def __init__(
            self,
            prev_layer,
            n_filter=32,
            filter_size=(3, 3),
            strides=(1, 1),
            padding='SAME',
            act=None,
            bitW=8,
            bitA=8,
            use_gemm=False,
            use_cudnn_on_gpu=True,
            data_format=None,
            W_init=tf.truncated_normal_initializer(stddev=0.02),
            b_init=tf.constant_initializer(value=0.0),
            W_init_args=None,
            b_init_args=None,
            name='quan_cnn2d',
    ):
        super(QuantizedConv2d, self
             ).__init__(prev_layer=prev_layer, act=act, W_init_args=W_init_args, b_init_args=b_init_args, name=name)

        logging.info(
            "QuantizedConv2d %s: n_filter: %d filter_size: %s strides: %s pad: %s act: %s" % (
                self.name, n_filter, str(filter_size), str(strides), padding, self.act.__name__
                if self.act is not None else 'No Activation'
            )
        )

        self.inputs = quantize_active_overflow(self.inputs, bitA)  # Do not remove

        if use_gemm:
            raise Exception("TODO. The current version use tf.matmul for inferencing.")

        if len(strides) != 2:
            raise ValueError("len(strides) should be 2.")

        try:
            input_channels = int(prev_layer.outputs.get_shape()[-1])
        except TypeError:  # if input_channels is ?, it happens when using Spatial Transformer Net
            input_channels = 1
            logging.warning("[warnings] unknow input channels, set to 1")

        shape = (filter_size[0], filter_size[1], input_channels, n_filter)
        strides = (1, strides[0], strides[1], 1)

        with tf.variable_scope(name):
            W = self._get_tf_variable(
                name='W_conv2d', shape=shape, initializer=W_init, dtype=self.inputs.dtype, **self.W_init_args
            )

            W = quantize_weight_overflow(W, bitW)

            self.outputs = tf.nn.conv2d(
                self.inputs, W, strides=strides, padding=padding, use_cudnn_on_gpu=use_cudnn_on_gpu,
                data_format=data_format
            )

            if b_init:
                b = self._get_tf_variable(
                    name='b_conv2d', shape=(shape[-1]), initializer=b_init, dtype=self.inputs.dtype, **self.b_init_args
                )

                self.outputs = tf.nn.bias_add(self.outputs, b, name='bias_add')

            self.outputs = self._apply_activation(self.outputs)

        self._add_layers(self.outputs)
        self._add_params(self._local_weights)