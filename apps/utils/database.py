import logging
from contextlib import contextmanager
from functools import partial

from django.db import (
    transaction,
    connection,
)


logger = logging.getLogger(__name__)


# region advisory locks

LOCK_ID_SUBMITTAL_NUMBER_ASSIGNMENT = 10000


@contextmanager
def apply_advisory_lock(*lock_ids):
    assert 1 <= len(lock_ids) <= 2, (
        'Advisory lock IDs must be between 1 and 2 in length!',
    )

    if transaction.get_autocommit():
        raise RuntimeError(
            'Advisory lock attempted outside of transaction!',
        )

    cursor = connection.cursor()
    cursor.execute(
        'SELECT pg_advisory_xact_lock({})'.format(
            ', '.join(['%s'] * len(lock_ids)),
        ),
        lock_ids,
    )
    logger.debug('Acquired advisory lock for %s', tuple(lock_ids))

    yield


# This will sometimes be applied multiple times, which is okay. You can perform
# multiple `xact` locks within a single transaction and they will not block each
# other, but will instead only block other transactions from acquiring it, and
# "all" the acquired locks will be released as soon as the transaction ends
apply_advisory_lock_submittal_number_assignment = partial(
    apply_advisory_lock,
    # *lock_id_names value
    LOCK_ID_SUBMITTAL_NUMBER_ASSIGNMENT,
)

# endregion advisory locks
