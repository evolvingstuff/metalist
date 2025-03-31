/*
    TODO:

    I want to move away from using a state machine. It is just too restricting,
    and there are all sorts of "hacks" needed to make it work, but then it is
    no longer purely a state machine.

    For instance, instead of having the states 'editing', 'searching', and 'idle'
    I would want this data:
    modeEditing: bool
    modeSearching: bool

    'idle' can be inferred from modeEditing = False && modeSearching = False

    In fact, there isn't really a need to specify 'idle' at all, it's just the
    absense of other modes.

    but one thing we would want to add in is modeCallingApi (or some name like that)
    to reflect when calls to the server are being made. This is an example of where
    the classic state machine model breaks down, because instead of transitioning from
    A to B, you are really doing some stuff in between, and so you have to add memory
    to know what state to transition to upon getting a response from the server.

    I want the ModeManager object to contain all the vars that are currently in
    state-context.js (with some changes, like I just described). I want those vars
    to start with underscores, and use getters and setters for everything so
    we can add in state validation.

    I want all event handling done inside of this object. This will be more "imperative"
    in nature, but frankly, things are getting to abstract and non-local to reason about
    and it gets tougher and tougher to make even simple changes in the state machine
    paradigm.


 */