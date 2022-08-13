"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some basic exceptions used across the library.
"""


class SnakeCoreException(Exception):
    """A generic snakecore exception, the base class of all exceptions of the library."""


# utils/
## serializers
class DeserializationError(SnakeCoreException):
    """Failed to deserialize the serialized data of a serializer object."""


# jobs/
class JobException(SnakeCoreException):
    """Generic job object exception."""


class JobPermissionError(JobException):
    """Job object permisssion error."""


class JobStateError(JobException):
    """An invalid job object state is preventing an operation."""


class JobIsGuarded(JobException):
    """Job object is (already) being guarded."""


class JobNotAlive(JobStateError):
    """Job is not alive."""

    pass


class JobIsDone(JobNotAlive):
    """Job is not alive because it is already done."""

    pass


class JobNotRunning(JobStateError):
    """Job is not running."""

    pass


class JobAlreadyRegistered(JobStateError):
    """Exception class for job registration errors."""

    pass


class JobOutputError(JobStateError):
    """Exception class for job output related errors."""

    pass


class JobInitializationError(JobException):
    """Initialization of a job object failed, either due to it already being initialized or
    having an internal error.

    This is meant to be raised from the exception of the error if one is available as a cause.
    """


class JobWarning(Warning):
    """Base class for job related warnings."""


# storage/
class StorageException(SnakeCoreException):
    """Exceptions raised during Storage API handling"""
