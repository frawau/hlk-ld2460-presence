"""Temporary BlueZ pairing agent that accepts Just Works pairing.

The LD2460 refuses GATT reads on an unencrypted link. BlueZ then starts LE
pairing, which needs a registered agent to confirm it even though neither side
has a display or keypad. This agent confirms every request.

No ``from __future__ import annotations`` here: dbus_fast reads the D-Bus
signature from the literal annotation strings ("o", "u", "s").
"""

from dbus_fast.aio import MessageBus
from dbus_fast.constants import BusType
from dbus_fast.service import ServiceInterface, method

AGENT_PATH = "/ld2460/agent"


class _JustWorksAgent(ServiceInterface):
    def __init__(self):
        super().__init__("org.bluez.Agent1")

    @method()
    def Release(self): ...

    @method()
    def RequestAuthorization(self, device: "o"): ...

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"): ...

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"): ...

    @method()
    def Cancel(self): ...


class JustWorksAgent:
    """Async context manager registering the agent as BlueZ default agent."""

    async def __aenter__(self):
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self._bus.export(AGENT_PATH, _JustWorksAgent())
        intro = await self._bus.introspect("org.bluez", "/org/bluez")
        obj = self._bus.get_proxy_object("org.bluez", "/org/bluez", intro)
        self._manager = obj.get_interface("org.bluez.AgentManager1")
        await self._manager.call_register_agent(AGENT_PATH, "NoInputNoOutput")
        await self._manager.call_request_default_agent(AGENT_PATH)
        return self

    async def __aexit__(self, *exc):
        try:
            await self._manager.call_unregister_agent(AGENT_PATH)
        finally:
            self._bus.disconnect()
