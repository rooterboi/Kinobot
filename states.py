"""FSM holatlari."""
from aiogram.fsm.state import State, StatesGroup


class SecretStates(StatesGroup):
    pin = State()
    token = State()


class AddMovie(StatesGroup):
    video = State()
    title = State()
    year = State()
    quality = State()
    country = State()
    language = State()
    genre = State()
    code = State()


class DeleteMovie(StatesGroup):
    code = State()


class EditMovie(StatesGroup):
    code = State()
    field = State()
    value = State()


class ChannelStates(StatesGroup):
    add_sub = State()
    set_post = State()


class BroadcastStates(StatesGroup):
    content = State()
    confirm = State()
    button = State()


class SettingsStates(StatesGroup):
    gemini_key = State()
    new_pin = State()


class AIStates(StatesGroup):
    chat = State()


class LogoStates(StatesGroup):
    brand = State()
    style = State()
    done = State()
    edit = State()
    qa = State()


class AddSeries(StatesGroup):
    title = State()
    year = State()
    quality = State()
    country = State()
    language = State()
    genre = State()
    code = State()


class AddEpisode(StatesGroup):
    code = State()
    video = State()


class DeleteSeries(StatesGroup):
    code = State()


class DeleteEpisode(StatesGroup):
    code = State()
    number = State()


class EditSeries(StatesGroup):
    code = State()
    field = State()
    value = State()
