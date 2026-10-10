"""Create isolated semantic variants without editing the tracing baseline checkout."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/online-boutique/src"
OUT = ROOT / "data/mutations/method_controlled"
OUT.mkdir(parents=True, exist_ok=True)

CURRENCY = "currencyservice/server.js"
PAYMENT = "paymentservice/charge.js"
RECOMMENDATION = "recommendationservice/recommendation_server.py"
EMAIL = "emailservice/email_server.py"


def replace_once(content, before, after):
    if content.count(before) != 1:
        raise ValueError(f"Expected one match, found {content.count(before)}: {before[:100]}")
    return content.replace(before, after)


def variant(case_id, change_type, service, file, target, changes, description, mechanism):
    source_path = SOURCE / file
    content = source_path.read_text(encoding="utf-8")
    changed = content
    for before, after in changes:
        changed = replace_once(changed, before, after)
    case_dir = OUT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix
    out = case_dir / (source_path.stem + suffix)
    out.write_text(changed, encoding="utf-8")
    compose = case_dir / "compose.override.yml"
    compose.write_text(
        f"services:\n  {service}:\n    volumes:\n      - {out.as_posix()}:{target}:ro\n",
        encoding="utf-8",
    )
    manifest = {
        "case_id": case_id, "cohort": "controlled", "change_type": change_type,
        "changed_service": service, "changed_file": "src/" + file,
        "description": description, "expected_mechanism": mechanism,
        "original_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "changed_sha256": hashlib.sha256(changed.encode()).hexdigest(),
        "override": str(compose),
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def config(case_id, change_type, service, environment, description, mechanism):
    case_dir = OUT / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    lines = ["services:", f"  {service}:", "    environment:"]
    lines.extend(f"      {key}: '{value}'" for key, value in environment.items())
    compose = case_dir / "compose.override.yml"
    compose.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest = {
        "case_id": case_id, "cohort": "controlled", "change_type": change_type,
        "changed_service": service, "changed_file": "Compose environment",
        "description": description, "expected_mechanism": mechanism,
        "environment": environment, "override": str(compose),
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    cases = []
    add = cases.append
    # Logic: distinct pricing rules on a production conversion API.
    add(variant("L01_spread_05", "Logic", "currencyservice", CURRENCY, "/usr/src/app/server.js", [
        ("units: euros.units * data[request.to_code],\n        nanos: euros.nanos * data[request.to_code]", "units: euros.units * data[request.to_code] * 1.05,\n        nanos: euros.nanos * data[request.to_code] * 1.05")],
        "Apply 5% destination-currency spread", "Converted prices and checkout costs increase"))
    add(variant("L02_whole_units", "Logic", "currencyservice", CURRENCY, "/usr/src/app/server.js", [
        ("result.nanos = Math.floor(result.nanos);", "result.nanos = 0; // whole-unit pricing policy")],
        "Round converted prices down to whole currency units", "Fractional prices change"))
    add(variant("L03_minimum_10", "Logic", "currencyservice", CURRENCY, "/usr/src/app/server.js", [
        ("result.currency_code = request.to_code;", "if (result.units < 10) { result.units = 10; result.nanos = 0; }\n      result.currency_code = request.to_code;")],
        "Introduce a minimum converted amount of 10 units", "Low-priced products change"))
    add(variant("L04_cap_50", "Logic", "currencyservice", CURRENCY, "/usr/src/app/server.js", [
        ("result.currency_code = request.to_code;", "if (result.units >= 50) { result.units = 50; result.nanos = 0; }\n      result.currency_code = request.to_code;")],
        "Cap converted amounts at 50 units", "High-priced products change"))

    # API behavior: validation and supported-value contracts.
    add(variant("A01_drop_jpy", "API", "currencyservice", CURRENCY, "/usr/src/app/server.js", [
        ("currency_codes: Object.keys(data)", "currency_codes: Object.keys(data).filter(code => code !== 'JPY')")],
        "Withdraw JPY from advertised currencies", "Supported-currency API and frontend selector change"))
    add(variant("A02_reject_eur", "API", "currencyservice", CURRENCY, "/usr/src/app/server.js", [
        ("const request = call.request;", "const request = call.request;\n      if (request.to_code === 'EUR') { return callback({code: grpc.status.INVALID_ARGUMENT, message: 'EUR conversion disabled'}); }")],
        "Reject EUR as conversion target", "Convert EUR status changes"))
    add(variant("A03_accept_amex", "API", "paymentservice", PAYMENT, "/usr/src/app/charge.js", [
        ("cardType === 'visa' || cardType === 'mastercard'", "cardType === 'visa' || cardType === 'mastercard' || cardType === 'amex'")],
        "Accept AMEX cards in addition to Visa and MasterCard", "Charge AMEX error becomes success"))
    add(variant("A04_validate_email", "API", "emailservice", EMAIL, "/email_server/email_server.py", [
        ("class DummyEmailService(BaseEmailService):\n  def SendOrderConfirmation(self, request, context):\n", "class DummyEmailService(BaseEmailService):\n  def SendOrderConfirmation(self, request, context):\n    if '@' not in request.email:\n      context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'invalid recipient')\n")],
        "Validate recipient format in dummy email API", "Malformed email changes from success to INVALID_ARGUMENT"))

    # Dependency: replace the product-catalog interaction used by recommendations.
    two_lines = "cat_response = product_catalog_stub.ListProducts(demo_pb2.Empty())\n        product_ids = [x.id for x in cat_response.products]"
    add(variant("D01_local_cache", "Dependency", "recommendationservice", RECOMMENDATION, "/recommendationservice/recommendation_server.py", [
        (two_lines, "product_ids = ['66VCHSJNUP', '1YMWWN1N4O', 'L9ECAV7KIM', '2ZYFJ3GM2N', '0PUK6V6EV0', 'LS4PSXUNUM', '9SIQT8TOJO', '6E92ZMYYFZ']")],
        "Use a stale local catalog snapshot instead of catalog RPC", "Catalog call disappears and recommendation output changes"))
    add(variant("D02_search_mug", "Dependency", "recommendationservice", RECOMMENDATION, "/recommendationservice/recommendation_server.py", [
        ("product_catalog_stub.ListProducts(demo_pb2.Empty())", "product_catalog_stub.SearchProducts(demo_pb2.SearchProductsRequest(query='mug'))"),
        ("[x.id for x in cat_response.products]", "[x.id for x in cat_response.results]")],
        "Select candidates from catalog SearchProducts for mugs", "Catalog API dependency and recommendations change"))
    add(variant("D03_search_watch", "Dependency", "recommendationservice", RECOMMENDATION, "/recommendationservice/recommendation_server.py", [
        ("product_catalog_stub.ListProducts(demo_pb2.Empty())", "product_catalog_stub.SearchProducts(demo_pb2.SearchProductsRequest(query='watch'))"),
        ("[x.id for x in cat_response.products]", "[x.id for x in cat_response.results]")],
        "Select candidates from catalog SearchProducts for watches", "Catalog API dependency and recommendations change"))
    add(variant("D04_single_product", "Dependency", "recommendationservice", RECOMMENDATION, "/recommendationservice/recommendation_server.py", [
        (two_lines, "cat_response = product_catalog_stub.GetProduct(demo_pb2.GetProductRequest(id='1YMWWN1N4O'))\n        product_ids = [cat_response.id]")],
        "Use GetProduct for a featured product instead of ListProducts", "Catalog API dependency and recommendation output change"))

    # Configuration: data files and service address.
    catalog_file = "productcatalogservice/products.json"
    raw = json.loads((SOURCE / catalog_file).read_text(encoding="utf-8"))
    product = raw["products"][0]
    product["priceUsd"]["units"] = 24
    case_dir = OUT / "C01_catalog_price"
    case_dir.mkdir(parents=True, exist_ok=True)
    out = case_dir / "products.json"
    out.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    compose = case_dir / "compose.override.yml"
    compose.write_text(f"services:\n  productcatalogservice:\n    volumes:\n      - {out.as_posix()}:/src/products.json:ro\n", encoding="utf-8")
    manifest = {"case_id": "C01_catalog_price", "cohort": "controlled", "change_type": "Configuration", "changed_service": "productcatalogservice", "changed_file": "src/" + catalog_file, "description": "Raise sunglasses catalog price from $19.99 to $24.99", "expected_mechanism": "Catalog, frontend, checkout outputs change", "override": str(compose)}
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    add(manifest)
    add(variant("C02_exchange_rate", "Configuration", "currencyservice", "currencyservice/data/currency_conversion.json", "/usr/src/app/data/currency_conversion.json", [
        ('"USD": "1.1305"', '"USD": "1.2000"')],
        "Update USD exchange-rate data from 1.1305 to 1.2000", "Cross-currency conversions change"))
    add(config("C03_cart_address", "Configuration", "frontend", {"CART_SERVICE_ADDR": "productcatalogservice:3550"},
               "Misconfigure frontend cart dependency address", "Cart-dependent HTTP paths return errors"))

    # Failure and fallback policy.
    add(variant("F01_payment_limit", "Failure/Fallback", "paymentservice", PAYMENT, "/usr/src/app/charge.js", [
        ("if (!valid) { throw new InvalidCreditCard(); }", "if (!valid) { throw new InvalidCreditCard(); }\n  if (amount.units >= 19) { throw new CreditCardError('payment limit exceeded'); }")],
        "Reject charges of at least 19 currency units", "Checkout payment failure and Charge error"))
    add(variant("F02_unknown_currency_fallback", "Failure/Fallback", "currencyservice", CURRENCY, "/usr/src/app/server.js", [
        ("units: euros.units * data[request.to_code],\n        nanos: euros.nanos * data[request.to_code]", "units: euros.units * (data[request.to_code] || data.USD),\n        nanos: euros.nanos * (data[request.to_code] || data.USD)"),
        ("result.currency_code = request.to_code;", "result.currency_code = data[request.to_code] ? request.to_code : 'USD';")],
        "Fall back to USD for unknown destination currencies", "Unknown target Convert behavior changes"))
    add(variant("F03_block_test_mail", "Failure/Fallback", "emailservice", EMAIL, "/email_server/email_server.py", [
        ("class DummyEmailService(BaseEmailService):\n  def SendOrderConfirmation(self, request, context):\n", "class DummyEmailService(BaseEmailService):\n  def SendOrderConfirmation(self, request, context):\n    if request.email.endswith('.test'):\n      context.abort(grpc.StatusCode.PERMISSION_DENIED, 'test mail delivery disabled')\n")],
        "Block delivery to .test recipients", "SendOrderConfirmation returns PERMISSION_DENIED while checkout logs tolerated failure"))

    (OUT / "cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(json.dumps({"case_count": len(cases), "types": {t: sum(c["change_type"] == t for c in cases) for t in sorted({c["change_type"] for c in cases})}}, indent=2))


if __name__ == "__main__":
    main()
