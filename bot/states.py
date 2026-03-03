from aiogram.fsm.state import State, StatesGroup


class BookingFlow(StatesGroup):
    choose_org = State()
    choose_resource = State()
    choose_date = State()
    choose_slot_start = State()
    choose_slot_end = State()
    enter_name = State()
    enter_phone = State()
    enter_comment = State()
    confirm = State()
