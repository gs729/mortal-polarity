import functools
import operator

import hikari

from lightbulb import context as context_
from lightbulb import errors
from lightbulb.utils import permissions
from lightbulb.checks import _guild_only
from lightbulb.checks import Check


async def _has_guild_permissions(
    context: context_.base.Context, *, perms: hikari.Permissions
) -> bool:
    _guild_only(context)

    channel = context.get_channel()
    if channel is None:
        await context.bot.rest.fetch_channel(context.channel_id)

    assert context.member is not None and isinstance(channel, hikari.GuildChannel)
    missing_perms = ~permissions.permissions_in(channel, context.member) & perms
    if missing_perms is not hikari.Permissions.NONE:
        raise errors.MissingRequiredPermission(
            "You are missing one or more permissions required in order to run this command",
            perms=missing_perms,
        )
    return True


def has_guild_permissions(
    perm1: hikari.Permissions, *perms: hikari.Permissions
) -> Check:
    """
    Custom Async version of `lightbulb.checks.has_guild_permissions`
    Prevents the command from being used by a member missing any of the required
    permissions (this takes into account permissions granted by both roles and permission overwrites).

    Args:
        perm1 (:obj:`hikari.Permissions`): Permission to check for.
        *perms (:obj:`hikari.Permissions`): Additional permissions to check for.

    Note:
        This check will also prevent commands from being used in DMs, as you cannot have permissions
        in a DM channel.

    Warning:
        This check is unavailable if your application is stateless and/or missing the intent
        :obj:`hikari.Intents.GUILDS` and will **always** raise an error on command invocation if
        either of these conditions are not met.
    """
    reduced = functools.reduce(operator.or_, [perm1, *perms])
    return Check(functools.partial(_has_guild_permissions, perms=reduced))
