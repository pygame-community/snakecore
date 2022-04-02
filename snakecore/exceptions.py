"""
This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present PygameCommunityDiscord

This file defines some basic exceptions used across the library.
"""


class SnakeCoreException(Exception):
    """A generic snakecore exception, the base class of all exceptions of the library."""


# utils/
## serializers
class DeserializationError(SnakeCoreException):
    """Failed to deserialize the serialized data of a serializer object."""


# jobs/
class JobException(Exception):
    """Generic job object exception."""


class JobPermissionError(JobException):
    """Job object permisssion error."""


class JobStateError(JobException):
    """An invalid job object state is preventing an operation."""


class JobInitializationError(JobException):
    """Initialization of a job object failed."""


class JobWarning(Warning):
    """Base class for job related warnings."""
