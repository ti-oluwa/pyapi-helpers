import sqlalchemy as sa
import sqlalchemy_utils as sa_utils
import base64
import typing
import time
import fastapi

from src.fastapi.sqlalchemy import models, mixins
from src.generics.utils.totp import TOTP, random_hex
from src.fastapi.config import settings
from src.fastapi.utils.requests import get_ip_address


class TimeBasedOTP(  # type: ignore
    mixins.TimestampMixin,
    mixins.UUID7PrimaryKeyMixin,
    models.Model,
):
    """Model representing a time-based one-time password."""

    __abstract__ = True

    key = sa.Column(
        sa.String(100),
        default=random_hex,
        unique=True,
        nullable=False,
        doc="Secret key used to generate OTP",
    )
    last_verified_counter = sa.Column(
        sa.Integer,
        default=-1,
        nullable=False,
        doc="Counter value of last verified token",
    )
    validity_period = sa.Column(
        sa.Integer,
        default=settings.get("OTP_VALIDITY_PERIOD", 3600),
        nullable=False,
        doc="Validity period of the OTP token in seconds",
    )
    length = sa.Column(
        sa.Integer,
        default=settings.get("OTP_LENGTH", 6),
        nullable=False,
        doc="Length of the OTP token in digits",
    )
    requestor_ip_address = sa.Column(
        sa_utils.IPAddressType,
        nullable=True,
        doc="IP address of the requestor. Will be used to verify the requestor if provided.",
    )
    extradata = sa.Column(sa.JSON, nullable=True, doc="Additional metadata")

    def totp(self) -> TOTP:
        """Constructs and returns a `TOTP` representation of the instance"""
        totp = TOTP(
            key=base64.b64encode(self.key.encode()),
            step=self.validity_period,  # type: ignore
            digits=self.length,  # type: ignore
        )
        # the current time will be used to generate a counter
        totp.time = time.time()
        return totp

    def token(self) -> str:
        """The OTP token"""
        totp = self.totp()
        token = str(totp.token()).zfill(self.length)  # type: ignore
        return token

    def verify_token(
        self,
        token: str,
        *,
        request: typing.Optional[fastapi.Request] = None,
        tolerance: int = 0,
    ) -> bool:
        """
        Verifies the OTP token.

        :param token: The OTP token to verify
        :param request: The request object
        :param tolerance: Number of seconds to allow for clock drift
        """
        try:
            int_token = int(token)
        except ValueError:
            return False

        ip_address = get_ip_address(request) if request else None
        # Ensure that the same device/machine that
        # requested the token's creation is the one verifying
        if (ip_address and self.requestor_ip_address) and (
            ip_address.exploded != str(self.requestor_ip_address)  # type: ignore
        ):
            return False

        totp = self.totp()
        # check if the current counter value is higher than the value of
        # last verified counter and check if entered token is correct by
        # calling totp.verify_token()
        if (totp.t() > self.last_verified_counter) and totp.verify(  # type: ignore
            int_token, tolerance=tolerance
        ):
            # if the condition is true, set the last verified counter value
            # to current counter value, and return True
            self.last_verified_counter = totp.t()
            return True
        # if the token entered was invalid or if the counter value
        # was less than last verified counter, then return False
        return False
