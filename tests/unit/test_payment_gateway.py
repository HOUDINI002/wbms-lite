"""Tests for the payment gateway contract, the mock and the factory."""

from __future__ import annotations

import dataclasses
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from wbms.gateways.payments import (
    GatewayConfigError,
    GatewayError,
    GatewayReceipt,
    GatewayResult,
    GatewayStatus,
    MockPaymentGateway,
    PaymentGateway,
    get_gateway,
)

SUCCESS_PHONE = "254712345671"
FAIL_PHONE = "254712345670"
PENDING_PHONE = "254712345679"


@pytest.fixture
def gateway() -> MockPaymentGateway:
    return MockPaymentGateway()


# -- contract ---------------------------------------------------------------------


def test_mock_satisfies_protocol(gateway: MockPaymentGateway) -> None:
    assert isinstance(gateway, PaymentGateway)


def test_return_types_are_frozen() -> None:
    receipt = GatewayReceipt("c1", GatewayStatus.PENDING)
    result = GatewayResult(GatewayStatus.SUCCESS, "R1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        receipt.checkout_id = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = GatewayStatus.FAILED  # type: ignore[misc]


def test_result_receipt_defaults_to_none() -> None:
    assert GatewayResult(GatewayStatus.PENDING).receipt_number is None


# -- mock behavior ----------------------------------------------------------------


def test_initiate_returns_pending_receipt_with_checkout_id(gateway: MockPaymentGateway) -> None:
    receipt = gateway.initiate(SUCCESS_PHONE, 50, "tx-1")
    assert receipt.status is GatewayStatus.PENDING
    assert receipt.checkout_id


def test_phone_ending_in_other_digit_succeeds(gateway: MockPaymentGateway) -> None:
    for digit in "12345678":
        receipt = gateway.initiate(f"25471234567{digit}", 50, "tx")
        result = gateway.query(receipt.checkout_id)
        assert result.status is GatewayStatus.SUCCESS
        assert result.receipt_number


def test_phone_ending_in_zero_fails(gateway: MockPaymentGateway) -> None:
    receipt = gateway.initiate(FAIL_PHONE, 50, "tx-1")
    result = gateway.query(receipt.checkout_id)
    assert result == GatewayResult(GatewayStatus.FAILED, None)


def test_phone_ending_in_nine_stays_pending(gateway: MockPaymentGateway) -> None:
    receipt = gateway.initiate(PENDING_PHONE, 50, "tx-1")
    for _ in range(3):
        assert gateway.query(receipt.checkout_id) == GatewayResult(GatewayStatus.PENDING, None)


def test_checkout_ids_and_receipts_are_unique(gateway: MockPaymentGateway) -> None:
    r1 = gateway.initiate(SUCCESS_PHONE, 50, "tx-1")
    r2 = gateway.initiate(SUCCESS_PHONE, 50, "tx-2")
    assert r1.checkout_id != r2.checkout_id
    assert (
        gateway.query(r1.checkout_id).receipt_number != gateway.query(r2.checkout_id).receipt_number
    )


def test_results_are_deterministic_across_instances() -> None:
    a, b = MockPaymentGateway(), MockPaymentGateway()
    ra = a.initiate(SUCCESS_PHONE, 50, "tx")
    rb = b.initiate(SUCCESS_PHONE, 50, "tx")
    assert ra == rb
    assert a.query(ra.checkout_id) == b.query(rb.checkout_id)


# -- call recording ---------------------------------------------------------------


def test_calls_are_recorded_in_order(gateway: MockPaymentGateway) -> None:
    receipt = gateway.initiate(SUCCESS_PHONE, 75, "tx-9")
    gateway.query(receipt.checkout_id)

    assert [c.method for c in gateway.calls] == ["initiate", "query"]
    assert gateway.calls[0].args == {
        "phone": SUCCESS_PHONE,
        "amount_kes": 75,
        "reference": "tx-9",
    }
    assert gateway.calls[1].args == {"checkout_id": receipt.checkout_id}


def test_calls_to_filters_by_method(gateway: MockPaymentGateway) -> None:
    receipt = gateway.initiate(SUCCESS_PHONE, 50, "tx-1")
    gateway.query(receipt.checkout_id)
    gateway.query(receipt.checkout_id)
    assert len(gateway.calls_to("initiate")) == 1
    assert len(gateway.calls_to("query")) == 2


# -- errors -----------------------------------------------------------------------


def test_query_unknown_checkout_raises(gateway: MockPaymentGateway) -> None:
    with pytest.raises(GatewayError):
        gateway.query("does-not-exist")


@pytest.mark.parametrize(
    ("phone", "amount", "reference"),
    [
        ("not-digits", 50, "tx"),
        ("", 50, "tx"),
        (SUCCESS_PHONE, 0, "tx"),
        (SUCCESS_PHONE, -5, "tx"),
        (SUCCESS_PHONE, True, "tx"),
        (SUCCESS_PHONE, 50.5, "tx"),
        (SUCCESS_PHONE, 50, ""),
        (SUCCESS_PHONE, 50, "   "),
    ],
)
def test_initiate_rejects_bad_arguments(
    gateway: MockPaymentGateway, phone: str, amount: int, reference: str
) -> None:
    with pytest.raises(GatewayError):
        gateway.initiate(phone, amount, reference)


def test_fail_with_simulates_outage(gateway: MockPaymentGateway) -> None:
    gateway.fail_with = GatewayError("provider down")
    with pytest.raises(GatewayError, match="provider down"):
        gateway.initiate(SUCCESS_PHONE, 50, "tx-1")
    with pytest.raises(GatewayError, match="provider down"):
        gateway.query("anything")
    # the attempts are still recorded
    assert len(gateway.calls) == 2

    gateway.fail_with = None
    assert gateway.initiate(SUCCESS_PHONE, 50, "tx-2").checkout_id


# -- settle helper ----------------------------------------------------------------


def test_settle_resolves_a_pending_payment(gateway: MockPaymentGateway) -> None:
    receipt = gateway.initiate(PENDING_PHONE, 50, "tx-1")
    gateway.settle(receipt.checkout_id, GatewayStatus.SUCCESS)
    result = gateway.query(receipt.checkout_id)
    assert result.status is GatewayStatus.SUCCESS
    assert result.receipt_number


def test_settle_with_explicit_receipt_and_failure_clears_receipt(
    gateway: MockPaymentGateway,
) -> None:
    receipt = gateway.initiate(PENDING_PHONE, 50, "tx-1")
    gateway.settle(receipt.checkout_id, GatewayStatus.SUCCESS, "ABC123")
    assert gateway.query(receipt.checkout_id).receipt_number == "ABC123"
    gateway.settle(receipt.checkout_id, GatewayStatus.FAILED, "ABC123")
    assert gateway.query(receipt.checkout_id) == GatewayResult(GatewayStatus.FAILED, None)


def test_settle_unknown_checkout_raises(gateway: MockPaymentGateway) -> None:
    with pytest.raises(GatewayError):
        gateway.settle("nope", GatewayStatus.SUCCESS)


def test_concurrent_initiates_get_unique_ids(gateway: MockPaymentGateway) -> None:
    ids: list[str] = []

    def work() -> None:
        for _ in range(25):
            ids.append(gateway.initiate(SUCCESS_PHONE, 50, "tx").checkout_id)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ids) == 200
    assert len(set(ids)) == 200


# -- factory ----------------------------------------------------------------------


def test_factory_returns_mock() -> None:
    gw = get_gateway(SimpleNamespace(PAYMENT_GATEWAY="mock"))
    assert isinstance(gw, MockPaymentGateway)


def test_factory_is_case_and_space_insensitive() -> None:
    assert isinstance(get_gateway(SimpleNamespace(PAYMENT_GATEWAY=" Mock ")), MockPaymentGateway)


def test_factory_defaults_to_mock_when_unset() -> None:
    assert isinstance(get_gateway(SimpleNamespace()), MockPaymentGateway)


def test_factory_returns_a_new_instance_each_call() -> None:
    settings = SimpleNamespace(PAYMENT_GATEWAY="mock")
    assert get_gateway(settings) is not get_gateway(settings)


def test_factory_rejects_unknown_name() -> None:
    with pytest.raises(GatewayConfigError, match="paypal"):
        get_gateway(SimpleNamespace(PAYMENT_GATEWAY="paypal"))


def test_factory_daraja_without_adapter_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "wbms.gateways.payments.daraja", raising=False)
    # ensure the import really fails even if a daraja module is later added
    monkeypatch.setitem(sys.modules, "wbms.gateways.payments.daraja", None)
    with pytest.raises(GatewayConfigError):
        get_gateway(SimpleNamespace(PAYMENT_GATEWAY="daraja"))


def test_factory_daraja_uses_adapter_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ModuleType("wbms.gateways.payments.daraja")

    class DarajaGateway:
        def __init__(self, settings: object) -> None:
            self.settings = settings

    fake.DarajaGateway = DarajaGateway  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "wbms.gateways.payments.daraja", fake)

    settings = SimpleNamespace(PAYMENT_GATEWAY="daraja")
    gw = get_gateway(settings)
    assert isinstance(gw, DarajaGateway)
    assert gw.settings is settings
