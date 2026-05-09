import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import logging
logging.getLogger('absl').setLevel(logging.ERROR)

import math
import numpy as np
import tensorflow as tf
from decimal import *

getcontext().prec = 10


#############################
# Global performance metric #
#############################
def calcPavg(C, N):
    alpha = 0.01
    p_global = C
    p_globalprime = p_global + 2.576 * \
        math.sqrt(float(p_global)*(1-p_global)/(N-1))
    return p_globalprime


##########################################
# Local performance metric               #
# p is probability of correct prediction #
# r is length of longest run             #
##########################################

def find_max_run(correct):
    run = 0
    maxrun = 0
    for i in correct:
        if i == 0:
            if run > maxrun:
                maxrun = run
            run = 0
        elif i == 1:
            run += 1
        else:
            raise ValueError("correct array contains non-binary values")
    if run > maxrun:
        maxrun = run
    return maxrun


def find_root(p, r):
    p = Decimal(str(p))
    q = 1-p
    s = Decimal(1)
    for i in range(10):
        s = 1+q*(p**r)*(s**(r+1))
    return s


def calc_qn(p, r, n):
    p = Decimal(str(p))
    q = 1-p
    x = Decimal(str(find_root(p, r)))
    qn = (1-p*x)/Decimal((r+1-r*x)*q)
    qn = qn/(x**(n+1))
    return qn


def calc_run(correct, verbose=False):
    N = len(correct)
    alpha = 0.99
    r = find_max_run(correct)
    alpha = Decimal(str(alpha))
    p = Decimal(str(0.5))
    adj = Decimal(str(0.5))
    qn = calc_qn(p, r+1, N)
    for i in range(30):
        adj /= 2
        if qn > alpha:
            p += adj
        else:
            p -= adj
        qn = calc_qn(p, r+1, N)
        if abs(qn-alpha) <= 0.0001:
            break
    return p


################################
# read data and generate batch #
################################
def gen_batch(X, batch_size, num_steps):
    x_steps_num = len(X)-num_steps-1
    for k in range(x_steps_num):
        x_steps = X[k:k+num_steps]
    xseq = np.zeros([batch_size, num_steps], dtype=np.int32)
    yseq = np.zeros([batch_size], dtype=np.int32)
    batch_partition_length = x_steps_num // batch_size
    for m in range(batch_partition_length):
        for i in range(batch_size):
            xseq[i] = X[m*batch_size+i:m*batch_size+i+num_steps]
            yseq[i] = X[m*batch_size+i+num_steps]
        yield xseq, yseq


##############
# FC network #
##############
def FC(dataset, bits_per_symbol, verbose=False):
    len_dataset = len(dataset)
    num_steps = 20
    batch_size = 20
    num_classes = 2**bits_per_symbol
    max_grad_norm = 5
    testdata_size = len_dataset // batch_size
    N = testdata_size // 100

    model = tf.keras.Sequential([
        tf.keras.layers.InputLayer(input_shape=(num_steps,)),
        tf.keras.layers.Dense(10, activation='tanh'),
        tf.keras.layers.Dense(5, activation='tanh'),
        tf.keras.layers.Dense(num_classes),
    ])

    optimizer = tf.keras.optimizers.SGD(clipnorm=max_grad_norm)
    loss_fn = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)

    av_accuracy = 0
    min_entropy = float('inf')

    for step, (x_batch, y_batch) in enumerate(gen_batch(dataset, batch_size, num_steps)):
        x_tensor = tf.constant(x_batch, dtype=tf.float32)
        y_tensor = tf.constant(y_batch, dtype=tf.int32)

        if step < testdata_size / 3:
            lr = 0.1
        elif step < testdata_size / 1.5:
            lr = 0.01
        else:
            lr = 0.01
        optimizer.learning_rate.assign(lr)

        with tf.GradientTape() as tape:
            logits = model(x_tensor, training=True)
            loss = loss_fn(y_tensor, logits)

        grads = tape.gradient(loss, model.trainable_variables)
        optimizer.apply_gradients(zip(grads, model.trainable_variables))

        correct = tf.equal(tf.argmax(logits, 1), y_tensor)
        train_accuracy = tf.reduce_mean(tf.cast(correct, tf.float32))
        av_accuracy += float(train_accuracy)

        if step % N == 0 and step > 0:
            p = av_accuracy / N
            Pavg = calcPavg(p, len_dataset)
            min_entropy = -math.log(Pavg, 2)
            if verbose:
                print("accuracy", p, "min_entropy", min_entropy)
            if min_entropy < 0.01:
                return min_entropy
            av_accuracy = 0

    return min_entropy


###############
# RNN network #
###############
def RNN(dataset, bits_per_symbol, verbose=False):
    len_dataset = len(dataset)
    num_steps = 20
    batch_size = 20
    num_classes = 2**bits_per_symbol
    hidden_size = num_steps + 1
    testdata_size = len(dataset) // batch_size
    N = testdata_size // 100
    max_grad_norm = 5

    cell = tf.keras.layers.SimpleRNNCell(hidden_size, activation='relu')
    rnn_layer = tf.keras.layers.RNN(cell, return_sequences=True)
    softmax_layer = tf.keras.layers.Dense(num_classes)

    optimizer = tf.keras.optimizers.SGD(clipnorm=max_grad_norm)
    loss_fn = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)

    av_accuracy = 0
    min_entropy = float('inf')

    for step, (x_batch, y_batch) in enumerate(gen_batch(dataset, batch_size, num_steps)):
        x_onehot = tf.one_hot(x_batch, num_classes)
        x_tensor = tf.constant(x_onehot, dtype=tf.float32)
        y_tensor = tf.constant(y_batch, dtype=tf.int32)

        if step < testdata_size / 3:
            lr = 0.1
        elif step < testdata_size / 1.5:
            lr = 0.01
        else:
            lr = 0.01
        optimizer.learning_rate.assign(lr)

        with tf.GradientTape() as tape:
            rnn_outputs = rnn_layer(x_tensor)
            final_state = rnn_outputs[:, num_steps - 1, :]
            logits = softmax_layer(final_state)
            loss = loss_fn(y_tensor, logits)

        grads = tape.gradient(loss, rnn_layer.trainable_variables + softmax_layer.trainable_variables)
        optimizer.apply_gradients(zip(
            grads,
            rnn_layer.trainable_variables + softmax_layer.trainable_variables
        ))

        correct = tf.equal(tf.argmax(logits, 1), y_tensor)
        train_accuracy = tf.reduce_mean(tf.cast(correct, tf.float32))
        av_accuracy += float(train_accuracy)

        if step % N == 0 and step > 0:
            p = av_accuracy / N
            Pavg = calcPavg(p, len_dataset)
            min_entropy = -math.log(Pavg, 2)
            if verbose:
                print("accuracy", p, "min_entropy", min_entropy)
            if min_entropy < 0.01:
                return min_entropy
            av_accuracy = 0

    return min_entropy
