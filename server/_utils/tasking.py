from functools import wraps, partial
from tornado import gen, concurrent
from tornado import ioloop

# Suppressed known DeprecationWarning for the futures backport
import warnings, exceptions
warnings.filterwarnings("ignore", "The futures package has been deprecated.*", exceptions.DeprecationWarning, "futures")
import futures

import logging
import sys
from futures import ThreadPoolExecutor

EXECUTOR = ThreadPoolExecutor(4)

_LINE = '%'*40


def safe_return_future(func):
    '''
        Identical to tornado.gen.return_future plus
        thread safety.  Executes the callback in 
        the ioloop thread
    '''
    @wraps(func)
    def exec_func(*args, **kwargs):

        future = concurrent.TracebackFuture()

        # accept optional callback
        callback = kwargs.pop('callback', None)
        if callback:
            future.add_done_callback(callback)

        try:

            io_loop = kwargs.pop('ioloop', None)
            if not io_loop:
                io_loop = ioloop.IOLoop.current()

            def _ioloop_callback(val):
                # print "set result to %s" % val
                future.set_result(val)

            def _callback(val):
                # set the result in the ioloop thread
                # print "callback val is %s " % val
                io_loop.add_callback(_ioloop_callback, val)

            # print "Func %s " % func
            func(callback=_callback, *args, **kwargs)
        except Exception:
            future.set_exc_info(sys.exc_info())

        return future

    exec_func.__doc__ = \
        ("%s\nsafe_return_future() wrapped function.\n" +
         "Runs asynchronously and returns a Future.\n" +
         "See _utils.concurrent for more info\n%s\n%s") % (_LINE, _LINE, exec_func.__doc__)
    return exec_func



def background_task(func):

    @wraps(func)
    def exec_background(*args, **kwargs):
        '''
            Executes a function in a background thread
            and returns a Future invoked when the thread completes.
            Useful for IO Bound processes that block.  For CPU
            bound processes consider using celery, DO NOT execute
            CPU Bound tasks in the tornado process!

            io_loop is the optional ioloop used to invoke the callback
            in the processing thread.  This is useful for unit tests
            that do not use the singleton ioloop.  If set to none,
            IOLoop.current() is returned
        '''
        # traceback future maintains python stack in exception
        future = concurrent.TracebackFuture()

        # use explicit ioloop for unit testing
        # Ref: https://github.com/tornadoweb/tornado/issues/663
        io_loop = kwargs.pop('ioloop', None)
        if not io_loop:
            io_loop = ioloop.IOLoop.current()

        # accept optional callback
        callback = kwargs.pop('callback', None)
        if callback:
            future.add_done_callback(callback)

        def _do_task(*args, **kwargs):
            try:
                rtn = func(*args, **kwargs)
                io_loop.add_callback(future.set_result, rtn)
            except Exception, e:
                logging.debug("Callback exception", exc_info=True)
                io_loop.add_callback(future.set_exc_info, sys.exc_info())

        EXECUTOR.submit(partial(_do_task, *args, **kwargs))
        return future

    exec_background.__doc__ = \
        ("%s\nbackground_task() wrapped function.\n" +
         "Runs asynchronously and returns a Future.\n" +
         "See _utils.concurrent for more info\n%s\n%s") % (_LINE, _LINE, exec_background.__doc__)
    return exec_background
