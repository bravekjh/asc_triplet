import torch
import numpy as np


def fit(train_loader, val_loader, model, loss_fn, optimizer, scheduler, n_epochs, log_interval, metrics=[],
        start_epoch=0, train_hist=None, val_hist=None, ckpter=None, logging=None):
    """
    fit model and test model
    :param train_loader:
    :param val_loader:
    :param model:
    :param loss_fn: loss function
    :param optimizer:
    :param scheduler:
    :param n_epochs: total epochs
    :param log_interval: print message every log_interval steps
    :param metrics: Accuracy or Non-zero triplets.
    :param start_epoch:
    :return: None
    """
    for epoch in range(0, start_epoch):
        scheduler.step()

    for epoch in range(start_epoch + 1, n_epochs + 1):
        scheduler.step()

        # train stage
        train_loss, metrics = train_epoch(train_loader, model, loss_fn, optimizer, log_interval, metrics)
        train_logs = dict()
        train_logs['loss'] = train_loss
        for metric in metrics:
            train_logs[metric.name()] = metric.value()
        if train_hist is not None:
            train_hist.add(logs=train_logs, epoch=epoch)
        # message = 'Epoch: {}/{}. Train set: Average loss: {:.4f}.'.format(epoch + 1, n_epochs, train_loss)
        # for metric in metrics:
        #     message += '\t{}: {}'.format(metric.name(), metric.value())

        # test stage
        if type(val_loader) is dict:
            for key in val_loader.keys():
                val_loss, metrics = test_epoch(val_loader[key], model, loss_fn, metrics)
                val_loss /= len(val_loader[key])
                val_logs = dict()
                val_logs['loss'] = val_loss
                for metric in metrics:
                    val_logs[metric.name()] = metric.value()
                if val_hist is not None:
                    val_hist[key].add(logs=val_logs, epoch=epoch)

            if val_hist is not None:
                train_hist.clear()
                train_hist.plot()
                for key in val_loader.keys():
                    val_hist[key].plot()
            if logging is not None:
                logging.info('Epoch{:04d}, {:15}, {}'.format(epoch, train_hist.name, str(train_hist.recent)))
                for key in val_loader.keys():
                    logging.info('Epoch{:04d}, {:15}, {}'.format(epoch, val_hist[key].name, str(val_hist[key].recent)))
            if ckpter is not None:
                ckpter.check_on(epoch=epoch, monitor='acc', loss_acc=val_hist['bc'].recent)
        else:

            val_loss, metrics = test_epoch(val_loader, model, loss_fn, metrics)
            val_loss /= len(val_loader)
            val_logs = dict()
            val_logs['loss'] = val_loss
            for metric in metrics:
                val_logs[metric.name()] = metric.value()
            if val_hist is not None:
                val_hist.add(logs=val_logs, epoch=epoch)

            if val_hist is not None:
                train_hist.clear()
                train_hist.plot()
                val_hist.plot()

            if logging is not None:
                logging.info('Epoch{:04d}, {:15}, {}'.format(epoch, train_hist.name, str(train_hist.recent)))
                logging.info('Epoch{:04d}, {:15}, {}'.format(epoch, val_hist.name, str(val_hist.recent)))
            if ckpter is not None:
                ckpter.check_on(epoch=epoch, monitor='acc', loss_acc=val_hist.recent)


def train_epoch(train_loader, model, loss_fn, optimizer, log_interval, metrics):
    for metric in metrics:
        metric.reset()

    model.train()
    losses = []
    total_loss = 0

    for batch_idx, (data, target) in enumerate(train_loader):
        target = target if len(target) > 0 else None
        if not type(data) in (tuple, list):
            data = (data,)
        data = tuple(d.cuda() for d in data)
        if target is not None:
            target = target.cuda()

        optimizer.zero_grad()
        outputs = model(*data)

        if type(outputs) not in (tuple, list):
            outputs = (outputs,)

        loss_inputs = outputs
        if target is not None:
            target = (target, )
            loss_inputs += target

        loss_outputs = loss_fn(*loss_inputs)
        loss = loss_outputs[0] if type(loss_outputs) in (tuple, list) else loss_outputs
        losses.append(loss.item())
        total_loss += loss.item()
        loss.backward()
        optimizer.step()

        for metric in metrics:
            metric(outputs, target, loss_outputs)

        if batch_idx % log_interval == 0:
            message = 'Train: [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(batch_idx * len(data[0]), len(train_loader.dataset),
                                                                      100 * batch_idx / len(train_loader), np.mean(losses))
            for metric in metrics:
                message += '\t{}: {}'.format(metric.name(), metric.value())

            print(message)
            losses = []
    total_loss /= (batch_idx + 1)
    return total_loss, metrics


def test_epoch(val_loader, model, loss_fn, metrics):
    with torch.no_grad():
        for metric in metrics:
            metric.reset()
        model.eval()
        val_loss = 0
        for batch_idx, (data, target) in enumerate(val_loader):
            target = target if len(target) > 0 else None
            if not type(data) in (tuple, list):
                data = (data,)
            data = tuple(d.cuda() for d in data)
            if target is not None:
                target = target.cuda()

            outputs = model(*data)

            if type(outputs) not in (tuple, list):
                outputs = (outputs,)
            loss_inputs = outputs
            if target is not None:
                target = (target,)
                loss_inputs += target

            loss_outputs = loss_fn(*loss_inputs)
            loss = loss_outputs[0] if type(loss_outputs) in (tuple, list) else loss_outputs
            val_loss += loss.item()

            for metric in metrics:
                metric(outputs, target, loss_outputs)

    return val_loss, metrics


def multi_device_train_epoch(train_loader, model, loss_fn, optimizer, log_interval, metrics):
    for metric in metrics:
        metric.reset()

    model.train()
    losses = []
    total_loss = 0
    total_batch = float(len(train_loader['a'].dataset)) / 180.0 * float(len(train_loader['b'].dataset)) / 180.0
    bc_batchs = float(len(train_loader['b'].dataset)) / 180.0
    for batch_idx, data_A in enumerate(train_loader['a']):
        for batch_idy, (data_B, data_C) in enumerate(zip(train_loader['b'], train_loader['c'])):
            data = torch.cat((data_A[0], data_B[0], data_C[0]), dim=0)
            target = torch.cat((data_A[1], data_B[1], data_C[1]), dim=0)
            if not type(data) in (tuple, list):
                data = (data,)
            data = tuple(d.cuda() for d in data)

            if target is not None:
                target = target.cuda()

            optimizer.zero_grad()
            outputs = model(*data)

            if type(outputs) not in (tuple, list):
                outputs = (outputs,)

            loss_inputs = outputs
            if target is not None:
                target = (target, )
                loss_inputs += target

            loss_outputs = loss_fn(*loss_inputs)
            loss = loss_outputs[0] if type(loss_outputs) in (tuple, list) else loss_outputs
            losses.append(loss.item())
            total_loss += loss.item()
            loss.backward()
            optimizer.step()

            for metric in metrics:
                metric(outputs, target, loss_outputs)
            cur_batch = batch_idx * bc_batchs + batch_idy
            if cur_batch % log_interval == 0:
                message = 'Train: [({:.0f}%)]\tLoss: {:.6f}'.format(100.0 * cur_batch / total_batch,
                                                                    np.mean(losses))
                print(message)
                losses = []

    total_loss /= ((batch_idx + 1) * (batch_idy + 1))
    return total_loss, metrics
