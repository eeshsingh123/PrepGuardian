---
trigger: always_on
description: Use this rule when working with the frontend folder and while building frontend of the application using React, Vite or Tanstacks
---

# Objective
I am planning to build a Learning/prep guardian which is essentially a Live AI Agent utilizing the Gemini Live API via Google's ADK.
The frontend is built using React, Vite & Tanstack. The user is still learning these things so be very careful with the changes made and double check before commiting on a fix.

## Code rules
1. Ensure that the frontend is clean, error-free and optimal.
2. Each component should be clearly separated and identifiable.
3. If a component is becoming bloated with a lot of code -s modularize it into multiple sub-components and separate them into different files and then use them.
4. The primary objective here is readable and optimal code.
5. Reponsive web design is also a priority

## API calling rules
1. Do not hardcode the api endpoint for the backend. Use an env variable constant to parse the endpoint BASE URL and then use it.
2. Ensure that the APIs are async ready and integrates well with the fastapi backend
3. Do not pass any sensitive information in the header and payload. If something like that comes up, clarify with the user.

## Error handling & Logging rules
1. Keep minimal try-catch blocks and make the code less bloated
2. If a flow is meant to fail - let it fail. Do not fail-safe the flow by parsing errors. Fail the code so it can be identified and fixed
3. Use user-friendly and readable logs wherever necessary. Define a separate log file with a logger and use that logger across all application with default as info. 
4. Do not do over-logging. Log only the important things each flow to understand and aid in debugging


## General Rule while building backend
1. Ask clarifying questions if something is unclear
2. Do not assume anything
3. Do not write unsafe and vulnerable code.
4. The user is not that well versed with Frotend development so the changes you make need to be to the point and easily readble and understandable.