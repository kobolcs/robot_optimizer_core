*** Settings ***
Documentation     Legacy checkout helpers awaiting refactor.

*** Keywords ***
Add Product To Cart
    [Arguments]    ${sku}
    Click Element    css=[data-sku='${sku}']

Proceed To Checkout
    Click Element    css:[data-testid='checkout-button']

Fill Shipping Form
    Input Text    id=shipping-name    Test Customer
    Input Text    id=shipping-address    123 Main St
    Input Text    id=shipping-city    Boston

Fill Card Details
    [Arguments]    ${card_number}    ${expiry}    ${cvv}
    Input Text    id=card-number    ${card_number}
    Input Text    id=card-expiry    ${expiry}
    Input Text    id=card-cvv    ${cvv}

Confirm Order
    Click Button    id=confirm-order

Verify Order Confirmation
    Page Should Contain    Thank you for your order

Sign In As Saved Customer
    Enter Credentials    customer.saved@example.com    Pa55word!
    Submit Login

Place Saved Cart Order
    Proceed To Checkout
    Confirm Order


Submit Login
    Click Element    css:button[type="submit"]

legacy helper
    Log    lower-case keyword name that violates team naming convention

Open Checkout Page
    [Arguments]    ${url}
    Go To    ${url}

Unused Legacy Tax Validation
    Log    Validates legacy tax rules for decommissioned checkout path
