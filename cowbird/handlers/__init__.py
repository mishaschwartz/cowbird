from typing import TYPE_CHECKING

from cowbird.handlers.handler_factory import HandlerFactory

if TYPE_CHECKING:
    from typing import List, Optional

    from cowbird.handlers.handler import Handler
    from cowbird.typedefs import AnySettingsContainer


def get_handlers(container=None):
    # type: (Optional[AnySettingsContainer]) -> List[Handler]
    """
    Obtains the handlers managed by the application.
    """
    return HandlerFactory().get_active_handlers()