"""Тесты для bot/scheduler.py — проактивные чек-ины должны трекать и удалять
своё предыдущее сообщение, чтобы не спамить чат (не эта же самая навигационная
карточка last_bot_msg_id из bot/helpers.py — отдельный ключ на каждый тип чек-ина)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.storage.memory import MemoryStorage

from bot.scheduler import _EVENING_MSG_KEY, _MORNING_MSG_KEY, _send_tracked, _state_for_user


def _fake_bot(message_id: int = 111):
    bot = MagicMock()
    bot.id = 999
    bot.delete_message = AsyncMock()
    sent = MagicMock()
    sent.message_id = message_id
    bot.send_message = AsyncMock(return_value=sent)
    return bot


class TestSendTracked:
    async def test_first_send_does_not_delete(self):
        bot = _fake_bot(message_id=1)
        storage = MemoryStorage()
        state = _state_for_user(bot, storage, telegram_user_id=123)

        await _send_tracked(bot, state, 123, _MORNING_MSG_KEY, "hello", None)

        bot.delete_message.assert_not_called()
        bot.send_message.assert_called_once_with(123, "hello", parse_mode=None)

    async def test_second_send_deletes_previous_message(self):
        bot = _fake_bot(message_id=1)
        storage = MemoryStorage()
        state = _state_for_user(bot, storage, telegram_user_id=123)

        await _send_tracked(bot, state, 123, _MORNING_MSG_KEY, "day 1", None)

        bot.send_message = AsyncMock(return_value=MagicMock(message_id=2))
        await _send_tracked(bot, state, 123, _MORNING_MSG_KEY, "day 2", None)

        bot.delete_message.assert_called_once_with(123, 1)

    async def test_delete_failure_does_not_block_send(self):
        bot = _fake_bot(message_id=1)
        storage = MemoryStorage()
        state = _state_for_user(bot, storage, telegram_user_id=123)
        await _send_tracked(bot, state, 123, _MORNING_MSG_KEY, "day 1", None)

        bot.delete_message = AsyncMock(side_effect=Exception("message to delete not found"))
        bot.send_message = AsyncMock(return_value=MagicMock(message_id=2))
        await _send_tracked(bot, state, 123, _MORNING_MSG_KEY, "day 2", None)

        bot.send_message.assert_called_once()

    async def test_morning_and_evening_keys_are_independent(self):
        bot = _fake_bot(message_id=1)
        storage = MemoryStorage()
        state = _state_for_user(bot, storage, telegram_user_id=123)

        await _send_tracked(bot, state, 123, _MORNING_MSG_KEY, "morning", None)
        bot.send_message = AsyncMock(return_value=MagicMock(message_id=2))
        await _send_tracked(bot, state, 123, _EVENING_MSG_KEY, "evening", None)

        # разные ключи — вечернее сообщение не должно удалять утреннее
        bot.delete_message.assert_not_called()

        data = await state.get_data()
        assert data[_MORNING_MSG_KEY] == 1
        assert data[_EVENING_MSG_KEY] == 2

    async def test_state_for_user_uses_chat_id_equal_user_id(self):
        bot = _fake_bot()
        storage = MemoryStorage()
        state = _state_for_user(bot, storage, telegram_user_id=555)
        assert state.key.chat_id == 555
        assert state.key.user_id == 555
        assert state.key.bot_id == bot.id
