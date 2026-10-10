"""Functional gRPC probes executed inside the recommendation service container.

This process does not initialize OpenTelemetry. Its outputs are independent of
the Jaeger traces used by runtime impact prediction.
"""

import json
import sys

import grpc
from google.protobuf.json_format import MessageToDict

sys.path.insert(0, "/recommendationservice")
import demo_pb2 as pb
import demo_pb2_grpc as stub


def run(address, service, method, request):
    with grpc.insecure_channel(address) as channel:
        client = getattr(stub, service + "Stub")(channel)
        try:
            response = getattr(client, method)(request, timeout=8)
            return {"status": "OK", "result": MessageToDict(response, preserving_proto_field_name=True)}
        except grpc.RpcError as exc:
            return {"status": exc.code().name, "detail": exc.details()}


def main():
    address = pb.Address(street_address="1 Experiment Way", city="Mountain View", state="CA", country="United States", zip_code=94043)
    product = pb.CartItem(product_id="OLJCESPC7Z", quantity=1)
    user = "cia-method-oracle"
    probes = {
        "CurrencyService.GetSupportedCurrencies": run("currencyservice:7000", "CurrencyService", "GetSupportedCurrencies", pb.Empty()),
        "CurrencyService.Convert.USD_USD": run("currencyservice:7000", "CurrencyService", "Convert", pb.CurrencyConversionRequest(**{"from": pb.Money(currency_code="USD", units=19, nanos=990000000), "to_code": "USD"})),
        "CurrencyService.Convert.USD_EUR": run("currencyservice:7000", "CurrencyService", "Convert", pb.CurrencyConversionRequest(**{"from": pb.Money(currency_code="USD", units=19, nanos=990000000), "to_code": "EUR"})),
        "CurrencyService.Convert.small_USD": run("currencyservice:7000", "CurrencyService", "Convert", pb.CurrencyConversionRequest(**{"from": pb.Money(currency_code="USD", units=8, nanos=990000000), "to_code": "USD"})),
        "CurrencyService.Convert.large_USD": run("currencyservice:7000", "CurrencyService", "Convert", pb.CurrencyConversionRequest(**{"from": pb.Money(currency_code="USD", units=109, nanos=990000000), "to_code": "USD"})),
        "CurrencyService.Convert.unknown_target": run("currencyservice:7000", "CurrencyService", "Convert", pb.CurrencyConversionRequest(**{"from": pb.Money(currency_code="USD", units=19, nanos=990000000), "to_code": "ZZZ"})),
        "ProductCatalogService.ListProducts": run("productcatalogservice:3550", "ProductCatalogService", "ListProducts", pb.Empty()),
        "ProductCatalogService.GetProduct": run("productcatalogservice:3550", "ProductCatalogService", "GetProduct", pb.GetProductRequest(id="OLJCESPC7Z")),
        "ProductCatalogService.GetProduct.missing": run("productcatalogservice:3550", "ProductCatalogService", "GetProduct", pb.GetProductRequest(id="DOES-NOT-EXIST")),
        "ProductCatalogService.SearchProducts": run("productcatalogservice:3550", "ProductCatalogService", "SearchProducts", pb.SearchProductsRequest(query="sunglasses")),
        "ShippingService.GetQuote": run("shippingservice:50051", "ShippingService", "GetQuote", pb.GetQuoteRequest(address=address, items=[product])),
        "ShippingService.ShipOrder": run("shippingservice:50051", "ShippingService", "ShipOrder", pb.ShipOrderRequest(address=address, items=[product])),
        "RecommendationService.ListRecommendations": run("recommendationservice:8080", "RecommendationService", "ListRecommendations", pb.ListRecommendationsRequest(user_id=user, product_ids=["66VCHSJNUP", "1YMWWN1N4O", "L9ECAV7KIM", "2ZYFJ3GM2N", "0PUK6V6EV0", "LS4PSXUNUM", "9SIQT8TOJO", "6E92ZMYYFZ"])),
        "AdService.GetAds": run("adservice:9555", "AdService", "GetAds", pb.AdRequest(context_keys=["accessories"])),
        "EmailService.SendOrderConfirmation": run("emailservice:5000", "EmailService", "SendOrderConfirmation", pb.SendOrderConfirmationRequest(email="cia-method@example.test", order=pb.OrderResult(order_id="cia-method-order", shipping_address=address, shipping_cost=pb.Money(currency_code="USD", units=8, nanos=990000000), items=[pb.OrderItem(item=product, cost=pb.Money(currency_code="USD", units=19, nanos=990000000))]))),
        "EmailService.SendOrderConfirmation.invalid": run("emailservice:5000", "EmailService", "SendOrderConfirmation", pb.SendOrderConfirmationRequest(email="not-an-email", order=pb.OrderResult(order_id="cia-method-order"))),
    }
    shipment = probes["ShippingService.ShipOrder"]
    if shipment["status"] == "OK":
        shipment["result"] = {"tracking_id_present": bool(shipment["result"].get("tracking_id"))}
    probes["CartService.EmptyCart"] = run("cartservice:7070", "CartService", "EmptyCart", pb.EmptyCartRequest(user_id=user))
    probes["CartService.AddItem"] = run("cartservice:7070", "CartService", "AddItem", pb.AddItemRequest(user_id=user, item=product))
    probes["CartService.GetCart"] = run("cartservice:7070", "CartService", "GetCart", pb.GetCartRequest(user_id=user))
    checkout = run("checkoutservice:5050", "CheckoutService", "PlaceOrder", pb.PlaceOrderRequest(
        user_id=user, user_currency="USD", address=address, email="cia-method@example.test",
        credit_card=pb.CreditCardInfo(credit_card_number="4111111111111111", credit_card_expiration_month=12, credit_card_expiration_year=2030, credit_card_cvv=123),
    ))
    if checkout["status"] == "OK":
        checkout["result"]["order"].pop("order_id", None)
        checkout["result"]["order"].pop("shipping_tracking_id", None)
    probes["CheckoutService.PlaceOrder"] = checkout
    payment = run("paymentservice:50051", "PaymentService", "Charge", pb.ChargeRequest(
        amount=pb.Money(currency_code="USD", units=19, nanos=990000000),
        credit_card=pb.CreditCardInfo(credit_card_number="4111111111111111", credit_card_expiration_month=12, credit_card_expiration_year=2030, credit_card_cvv=123),
    ))
    if payment["status"] == "OK":
        payment["result"] = {"transaction_id_present": bool(payment["result"].get("transaction_id"))}
    probes["PaymentService.Charge"] = payment
    for name, number, year in (
        ("amex", "378282246310005", 2030),
        ("expired", "4111111111111111", 2020),
    ):
        outcome = run("paymentservice:50051", "PaymentService", "Charge", pb.ChargeRequest(
            amount=pb.Money(currency_code="USD", units=19, nanos=990000000),
            credit_card=pb.CreditCardInfo(credit_card_number=number, credit_card_expiration_month=12, credit_card_expiration_year=year, credit_card_cvv=123),
        ))
        if outcome["status"] == "OK":
            outcome["result"] = {"transaction_id_present": bool(outcome["result"].get("transaction_id"))}
        probes["PaymentService.Charge." + name] = outcome
    print(json.dumps(probes, sort_keys=True))


if __name__ == "__main__":
    main()
