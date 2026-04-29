*** Settings ***
Documentation     Shared browser keywords for legacy storefront suite.

*** Variables ***
${LOGIN_URL}      https://staging-retail.example.internal/login

*** Keywords ***
Open Legacy Login Session
    Open Browser To Url    ${LOGIN_URL}
    Maximize Browser Window

Open Checkout Session
    Open Browser To Url    ${LOGIN_URL}

Close Session
    Capture Page Screenshot
    Close Browser

Click Login Button
    Click Button    css:button[type='submit']

Verify Dashboard Greeting
    Page Should Contain    Welcome back

Verify Login Error Message
    [Arguments]    ${expected_message}
    Page Should Contain    ${expected_message}

Open Browser To Url
    [Arguments]    ${url}
    Log    Opening ${url}

Enter Credentials
    [Arguments]    ${username}    ${password}
    Input Text    id=username    ${username}
    Input Password    id=password    ${password}
