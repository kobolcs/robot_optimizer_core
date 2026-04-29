*** Settings ***
Documentation     Authentication regression checks for customer web portal
Resource          resources/common.resource
Resource          resources/legacy_keywords.resource
Test Setup        Open Legacy Login Session
Test Teardown     Close Session

*** Test Cases ***
Valid User Can Sign In
    [Documentation]    Verifies that a known active customer can access account dashboard.
    [Tags]    smoke    auth    sprint-42
    Enter Credentials    qa.user@example.com    Pa55word!
    Sleep    2s
    Submit Login
    Verify Dashboard Greeting

Locked User Sees Account Disabled Message
    [Tags]    auth    regression
    Enter Credentials    locked.user@example.com    Pa55word!
    Submit Login
    Verify Login Error Message    Account disabled

*** Keywords ***
Submit Login
    Click Login Button
    Sleep    1 second
