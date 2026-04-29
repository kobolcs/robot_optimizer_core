*** Settings ***
Documentation     Checkout flow smoke and regression coverage for web storefront
Resource          resources/common.resource
Resource          resources/legacy_keywords.resource
Suite Setup       Open Checkout Session

*** Variables ***
${BASE_URL}       http://localhost:8080/shop

*** Test Cases ***
Guest Checkout With Card
    [Documentation]    Ensure guest checkout can complete with a valid card.
    [Tags]    checkout    smoke
    Open Checkout Page    ${BASE_URL}
    Add Product To Cart    sku-10014
    Proceed To Checkout
    Fill Shipping Form
    Fill Card Details    4111111111111111    12/29    123
    Sleep    5
    Confirm Order
    Verify Order Confirmation

Saved Customer Checkout
    [Tags]    checkout    e2e    high-priority
    Open Checkout Page    https://staging-retail.example.internal/shop
    Sign In As Saved Customer
    Place Saved Cart Order
    Verify Order Confirmation
