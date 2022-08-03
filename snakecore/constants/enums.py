"""This file is a part of the source code for snakecore.
This project has been licensed under the MIT license.
Copyright (c) 2022-present pygame-community

This file defines some enums and class namespaces used across the library.
"""


from enum import Enum, IntEnum, auto


class JobStatus(Enum):
    """An enum of constants representing the main statuses a job
    object can be in.
    """

    FRESH = auto()
    """This job object is freshly created and unmodified.
    """
    INITIALIZED = auto()

    STARTING = auto()
    RUNNING = auto()
    IDLING = auto()
    COMPLETING = auto()
    BEING_KILLED = auto()
    RESTARTING = auto()
    STOPPING = auto()
    OUTPUT_QUEUE_CLEARED = auto()

    STOPPED = auto()
    KILLED = auto()
    COMPLETED = auto()


class JobOps(Enum):
    """An enum of constants representing the operations that job
    objects can perform on each other with the supervision of a job manager.
    """

    CREATE = auto()
    """The act of creating/instantiating a job object.
    """
    INITIALIZE = auto()
    """The act of initializing a job object.
    """
    REGISTER = auto()
    """The act of registering a job object.
    """

    JOB_CLASS_REGISTER = auto()
    """The act of registering a job object's class into the job manager.
    """

    JOB_CLASS_UNREGISTER = auto()
    """The act of unregistering a job object's class from the job manager.
    """

    SCHEDULE = auto()
    """The act of scheduling a job type for instantiation in the future.
    """
    GUARD = auto()
    """The act of placing a modification guard on a job object.
    """

    FIND = auto()
    """The act of finding job objects based on specific parameters.
    """

    CUSTOM_EVENT_DISPATCH = auto()
    """The act of dispatching only custom events to job objects.
    """

    EVENT_DISPATCH = auto()
    """The act of dispatching any type of event to job objects.
    """

    START = auto()
    """The act of starting a job object.
    """
    STOP = auto()
    """The act of stopping a job object.
    """
    RESTART = auto()
    """The act of restarting a job object.
    """

    UNSCHEDULE = auto()
    """The act of unscheduling a specific job schedule operation.
    """
    UNGUARD = auto()
    """The act of removing a modification guard on a job object.
    """

    KILL = auto()
    """The act of killing a job object.
    """


_JOB_OPS_SIMP_PAST = dict(
    CREATE="CREATED",
    INITIALIZE="INITIALIZED",
    REGISTER="REGISTERED",
    JOB_CLASS_REGISTER="JOB_CLASS_REGISTERED",
    JOB_CLASS_UNREGISTER="JOB_CLASS_UNREGISTERED",
    SCHEDULE="SCHEDULED",
    GUARD="GUARDED",
    FIND="FOUND",
    CUSTOM_EVENT_DISPATCH="CUSTOM_EVENT_DISPATCHED",
    EVENT_DISPATCH="EVENT_DISPATCHED",
    START="STARTED",
    STOP="STOPPED",
    RESTART="RESTARTED",
    UNSCHEDULE="UNSCHEDULED",
    UNGUARD="UNGUARDED",
    KILL="KILLED",
)

_JOB_OPS_PRES_CONT = dict(
    CREATE="CREATING",
    INITIALIZE="INITIALIZING",
    REGISTER="REGISTERING",
    JOB_CLASS_REGISTER="JOB_CLASS_REGISTERING",
    JOB_CLASS_UNREGISTER="JOB_CLASS_UNREGISTERING",
    SCHEDULE="SCHEDULING",
    GUARD="GUARDING",
    FIND="FINDING",
    CUSTOM_EVENT_DISPATCH="CUSTOM_EVENT_DISPATCHING",
    EVENT_DISPATCH="EVENT_DISPATCHING",
    START="STARTING",
    STOP="STOPPING",
    RESTART="RESTARTING",
    UNSCHEDULE="UNSCHEDULING",
    UNGUARD="UNGUARDING",
    KILL="KILLING",
)


class JobStopReasons:
    """A class namespace of enums representing the different reasons job
    objects might stop running.
    """

    class Internal(Enum):
        """An enum of constants representing the different internal reasons job
        objects might stop running.
        """

        UNSPECIFIC = auto()
        """Job is stopping due to an unspecific internal reason.
        """
        ERROR = auto()
        """Job is stopping due to an internal error.
        """
        RESTART = auto()
        """Job is stopping due to an internal restart.
        """

        EXECUTION_COUNT_LIMIT = auto()
        """Job is stopping due to hitting its maximimum execution
        count before stopping.
        """

        COMPLETION = auto()
        """Job is stopping for finishing all execution, it has completed.
        """

        KILLING = auto()
        """Job is stopping due to killing itself internally.
        """

        EVENT_TIMEOUT = auto()
        """Job is stopping after reaching a timeout for receiving an event.
        """

        EMPTY_EVENT_QUEUE = auto()
        """Job is stopping due to an empty internal queue of received events.
        """

    class External(Enum):
        """An enum of constants representing the different external reasons job
        objects might stop running.
        """

        UNKNOWN = auto()
        """Job is stopping due to an unknown external reason.
        """

        RESTART = auto()
        """Job is stopping due to an external restart.
        """

        KILLING = auto()
        """Job is stopping due to being killed externally.
        """


class JobPermissionLevels(IntEnum):
    """An enum of constants representing the permission levels
    applicable to job objects.
    """

    LOWEST = 1
    """The lowest permission level.
    An Isolated job which has no information about other jobs being executed.
    Permissions:
        - Can manage its own execution at will.
    """

    LOW = 1 << 1
    """A low permission level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
    """

    MEDIUM = 1 << 2
    """The default permission level, with simple job management permissions.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
    """

    HIGH = 1 << 3
    """An elevated permission level, with additional control over jobs
    of a lower permission level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
        - Can stop, restart, kill or unschedule any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can dispatch custom events to other jobs (`CustomEvent` subclasses).
    """

    HIGHEST = 1 << 4
    """The highest usable permission level, with additional control over jobs
    of a lower permission level. Lower permissions additionally apply to this level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
        - Can stop, restart, kill or unschedule any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can guard and unguard jobs of the same permission level instantiated by itself.
        - Can dispatch custom events to other jobs (`CustomEvent` subclasses).
        - Can dispatch any event to other jobs (`BaseEvent` subclasses).
        - Can instantiate, register, start and schedule jobs of the same permission level.
        - Can stop, restart, kill or unschedule any job of the same permission level.
    """

    SYSTEM = 1 << 5
    """The highest possible permission level reserved for system-level jobs. Cannot be used directly.
    Lower permissions additionally apply to this level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register, start and schedule jobs of a lower permission level.
        - Can stop, restart, or kill jobs instantiated by itself or unschedule its scheduled jobs.
        - Can unschedule jobs that don't have an alive job as a scheduler.
        - Can stop, restart, kill or unschedule any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can dispatch custom events to other jobs (`CustomEvent` subclasses).
        - Can dispatch any event to other jobs (`BaseEvent` subclasses).
        - Can instantiate, register, start and schedule jobs of the same permission level.
        - Can stop, restart, kill or unschedule any job of the same permission level.
        - Can guard or unguard any job.
    """


class JobBoolFlags:
    """
    - `bool1 = bool2 = ... = True`:
        - `flags |= flag1 | flag2 | ...`
        - `flags = flags | flag1 | flag2 | ...`

    ...
    - `bool1 = bool2 = ... = False`:
        - `flags &= flags ^ (flag1 | flag2 | ...)`
        - `flags = flags & (flags ^ (flag1 | flag2 | ...))`

    ...
    - `bool1 = not bool1; bool2 = not bool2; ...`:
        - `flags ^= flag1 | flag2 | ...`
        - `flags = flags ^ (flag1 |flag2 | ...)`

    ...
    - `[not] bool1 is True`:
        - `[not] flags & flag1`

    ...
    - `[not] bool1 is False`:
        - `[not] not flags & flag1`

    ...
    - `[not] any(bool1, bool2, ...)`:
        - `[not] bool( flags & (flag1 | flag2 | ...) )`

    ...
    - `[not] all(bool1, bool2, ...)`:
        - `[not] (flags & (TRUE := flag1 | flag2 | ...) == TRUE)`
        - `[not] bool(flags & flag1 and flags & flag2 ...)`
        - `[not] (flags & (flag1 | flag2 | ...) == (flag1 | flag2 | ...))`

    ...
    """

    TRUE = 1
    FALSE = 0

    # _JobBase
    INITIALIZED = 1 << 0
    IS_INITIALIZING = 1 << 1

    IS_STARTING = 1 << 2
    IS_IDLING = 1 << 3

    TOLD_TO_STOP = 1 << 4
    TOLD_TO_STOP_BY_SELF = 1 << 5
    TOLD_TO_STOP_BY_FORCE = 1 << 6
    IS_STOPPING = 1 << 7
    STOPPED = 1 << 8

    TOLD_TO_RESTART = 1 << 9

    SKIP_NEXT_RUN = 1 << 10

    # ManagedJobBase
    COMPLETED = 1 << 11
    TOLD_TO_COMPLETE = 1 << 12

    KILLED = 1 << 13
    TOLD_TO_BE_KILLED = 1 << 14
    INTERNAL_STARTUP_KILL = 1 << 15
    EXTERNAL_STARTUP_KILL = 1 << 16

    # EventJobMixin
    CLEAR_EVENTS_AT_STARTUP = 1 << 17
    ALLOW_EVENT_QUEUE_OVERFLOW = 1 << 18
    BLOCK_EVENTS_ON_STOP = 1 << 19
    START_ON_DISPATCH = 1 << 20
    BLOCK_EVENTS_WHILE_STOPPED = 1 << 21
    ALLOW_DISPATCH = 1 << 22

    # EventJobBase
    OE_DISPATCH_ONLY_INITIAL = 1 << 23
    OE_AWAIT_DISPATCH = 1 << 24

    OE_STOP_AFTER_DISPATCH_TIMEOUT = 1 << 25
    OE_STOP_IF_NO_EVENTS = 1 << 26
    STOPPING_BY_EVENT_TIMEOUT = 1 << 27
    STOPPING_BY_EMPTY_QUEUE = 1 << 28
