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

        # EventJobMixin, MultiEventJobMixin

        EVENT_DISPATCH_TIMEOUT = auto()
        """Job is stopping after reaching a timeout for receiving an event.
        """

        EMPTY_EVENT_QUEUE = auto()
        """Job is stopping due to an empty internal event queue.
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

    LOW = 1
    """A low permission level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
    """

    MEDIUM = 1 << 1
    """An elevated permission level, with additional control over jobs
    of a lower permission level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register or start jobs of a lower permission level.
        - Can stop, restart or kill jobs instantiated by itself.
        - Can stop, restart or kill any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can dispatch custom events to other jobs (`CustomEvent` subclasses).
    """

    HIGH = 1 << 2
    """The highest usable permission level, with additional control over jobs
    of a lower permission level. Lower permissions additionally apply to this level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register or start jobs of a lower permission level.
        - Can stop, restart or kill jobs instantiated by itself.
        - Can stop, restart or kill any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can dispatch custom events to other jobs (`CustomEvent` subclasses).
        - Can dispatch any event to other jobs (`BaseEvent` subclasses).
        - Can instantiate, register or start jobs of the same permission level.
        - Can stop, restart or kill any job of the same permission level.
        - Can guard and unguard jobs of a lower or same permission level.
    """

    SYSTEM = 1 << 3
    """The highest possible permission level reserved for system-level jobs. Cannot be used directly.
    Lower permissions additionally apply to this level.

    Permissions:
        - Can manage its own execution at will.
        - Can discover and view all alive jobs, and request data from them.
        - Can instantiate, register or start jobs of a lower permission level.
        - Can stop, restart or kill jobs instantiated by itself.
        - Can stop, restart or kill any job of a lower permission level.
        - Can guard and unguard jobs of a lower permission level instantiated by itself.
        - Can dispatch custom events to other jobs (`CustomEvent` subclasses).
        - Can dispatch any event to other jobs (`BaseEvent` subclasses).
        - Can instantiate, register or start jobs of the same permission level.
        - Can stop, restart or kill any job of the same permission level.
        - Can guard and unguard jobs of a lower or same permission level.
        - Can guard or unguard any job.
    """


class JobBoolFlags:
    """Bit flags to be used by job classes for storing
    boolean values. Can be inherited and extended using
    the `LAST_FLAG_OFFSET` as a starting offset instead of 0.

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

    # _JobCore
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

    # BaseEventJobMixin
    CLEAR_EVENTS_AT_STARTUP = 1 << 17
    ALLOW_EVENT_QUEUE_OVERFLOW = 1 << 18
    BLOCK_EVENTS_ON_STOP = 1 << 19
    START_ON_EVENT_DISPATCH = 1 << 20
    BLOCK_EVENTS_WHILE_STOPPED = 1 << 21
    ALLOW_DOUBLE_EVENT_DISPATCH = 1 << 22
    EVENT_DISPATCH_ENABLED = 1 << 23
    STOP_ON_EMPTY_EVENT_QUEUE = 1 << 24

    # EventJobMixin
    OE_HANDLE_ONLY_INITIAL_EVENTS = 1 << 25
    AWAIT_EVENT_DISPATCH = 1 << 26
    STOP_ON_EVENT_DISPATCH_TIMEOUT = 1 << 27

    STOPPING_BY_EVENT_DISPATCH_TIMEOUT = 1 << 28
    STOPPING_BY_EMPTY_EVENT_QUEUE = 1 << 29

    # MultiEventJobMixin
    ALLOW_EVENT_SESSION_QUEUE_OVERFLOW = 1 << 30

    LAST_FLAG_OFFSET = 31
