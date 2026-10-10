"""Frozen endpoint universe, source-reviewed call graph and fixed rules.

Prepared before inspecting the controlled cohort scores. This is a small
hand-audited source graph, not a claim of whole-program static analysis.
"""

SERVICES = (
    "adservice", "cartservice", "checkoutservice", "currencyservice",
    "emailservice", "frontend", "paymentservice", "productcatalogservice",
    "recommendationservice", "shippingservice",
)

API_OWNERS = {
    "CartService.AddItem": "cartservice",
    "CartService.GetCart": "cartservice",
    "CartService.EmptyCart": "cartservice",
    "RecommendationService.ListRecommendations": "recommendationservice",
    "ProductCatalogService.ListProducts": "productcatalogservice",
    "ProductCatalogService.GetProduct": "productcatalogservice",
    "ProductCatalogService.SearchProducts": "productcatalogservice",
    "ShippingService.GetQuote": "shippingservice",
    "ShippingService.ShipOrder": "shippingservice",
    "CurrencyService.GetSupportedCurrencies": "currencyservice",
    "CurrencyService.Convert": "currencyservice",
    "PaymentService.Charge": "paymentservice",
    "EmailService.SendOrderConfirmation": "emailservice",
    "CheckoutService.PlaceOrder": "checkoutservice",
    "AdService.GetAds": "adservice",
    "frontend.GET_home": "frontend",
    "frontend.GET_product": "frontend",
    "frontend.POST_cart": "frontend",
    "frontend.GET_cart": "frontend",
    "frontend.POST_cart_empty": "frontend",
    "frontend.POST_set_currency": "frontend",
    "frontend.GET_logout": "frontend",
    "frontend.POST_checkout": "frontend",
    "frontend.GET_product_meta": "frontend",
    "frontend.GET_assistant": "frontend",
    "frontend.POST_bot": "frontend",
}
API_UNIVERSE = tuple(API_OWNERS)
SERVICE_UNIVERSE = SERVICES

# caller API -> callee API, audited against frontend/handlers.go, frontend/rpc.go,
# checkoutservice/main.go, recommendation_server.py. Only business calls count.
STATIC_CALLS = {
    "frontend.GET_home": (
        "CurrencyService.GetSupportedCurrencies", "ProductCatalogService.ListProducts",
        "CartService.GetCart", "CurrencyService.Convert", "AdService.GetAds"),
    "frontend.GET_product": (
        "ProductCatalogService.GetProduct", "CurrencyService.GetSupportedCurrencies",
        "CartService.GetCart", "CurrencyService.Convert",
        "RecommendationService.ListRecommendations", "AdService.GetAds"),
    "frontend.POST_cart": ("ProductCatalogService.GetProduct", "CartService.AddItem"),
    "frontend.GET_cart": (
        "CurrencyService.GetSupportedCurrencies", "CartService.GetCart",
        "RecommendationService.ListRecommendations", "ShippingService.GetQuote",
        "ProductCatalogService.GetProduct", "CurrencyService.Convert"),
    "frontend.POST_cart_empty": ("CartService.EmptyCart",),
    "frontend.POST_checkout": (
        "CheckoutService.PlaceOrder", "RecommendationService.ListRecommendations",
        "CurrencyService.GetSupportedCurrencies"),
    "frontend.GET_product_meta": ("ProductCatalogService.GetProduct",),
    "CheckoutService.PlaceOrder": (
        "CartService.GetCart", "ProductCatalogService.GetProduct",
        "CurrencyService.Convert", "ShippingService.GetQuote",
        "PaymentService.Charge", "ShippingService.ShipOrder",
        "CartService.EmptyCart", "EmailService.SendOrderConfirmation"),
    "RecommendationService.ListRecommendations": ("ProductCatalogService.ListProducts",),
}

# Source-reviewed typed constraints: checkout discards the email RPC error and
# never reads its Empty response; recommendation reads catalog product IDs but
# does not consume price fields. These rules apply only to S2 and B5.
IGNORED_RESPONSE_EDGES = {("CheckoutService.PlaceOrder", "EmailService.SendOrderConfirmation")}
PRICE_FIELD_UNUSED_EDGES = {("RecommendationService.ListRecommendations", "ProductCatalogService.ListProducts")}

# Fixed prediction policy, no fitted parameters or case-label access.
MAX_STATIC_API_DISTANCE = 2
FREQUENT_EDGE_MIN_CALLS = 2
HYBRID_STATIC_ONLY_LOW_COVERAGE_SCORE = 0.70
HYBRID_STATIC_ONLY_MID_COVERAGE_SCORE = 0.45
HYBRID_STATIC_ONLY_HIGH_COVERAGE_SCORE = 0.20
HYBRID_RUNTIME_ONLY_SCORE = 0.80
HYBRID_BOTH_SCORE = 1.0
HYBRID_THRESHOLD = 0.50
LOW_COVERAGE_CUTOFF = 0.40
HIGH_COVERAGE_CUTOFF = 0.70


def source_seeds(case):
    cid = case["case_id"]
    service = case["changed_service"]
    if service == "currencyservice":
        return {"CurrencyService.GetSupportedCurrencies"} if cid.startswith("A01") else {"CurrencyService.Convert"}
    if service == "productcatalogservice":
        return {"ProductCatalogService.ListProducts", "ProductCatalogService.GetProduct", "ProductCatalogService.SearchProducts"}
    if service == "recommendationservice":
        return {"RecommendationService.ListRecommendations"}
    if service == "shippingservice" and case["case_id"].startswith("R05"):
        return {"ShippingService.GetQuote"}
    if service == "emailservice":
        return {"EmailService.SendOrderConfirmation"}
    if service == "paymentservice":
        return {"PaymentService.Charge"}
    if service == "frontend":
        # Frontend address configuration is shared by all cart-using handlers.
        return {"frontend.GET_home", "frontend.GET_product", "frontend.POST_cart", "frontend.GET_cart"}
    return {api for api, owner in API_OWNERS.items() if owner == service}
