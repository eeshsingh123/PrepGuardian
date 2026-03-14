---
trigger: always_on
description: Use this rule when working with the backend folder and while building backend of the application using fastapi and python
---

# Objective
I am planning to build a Learning/prep guardian which is essentially a Live AI Agent utilizing the Gemini Live API via Google's ADK.
The backend is built using FastAPI and the database is async MongoDB (motor). Build clean, robust, optimal and type-safe API using FastAPI and Python. Use async operations as a priority but not a strict rule.

## IMPORTANT
1. We will use uv instead of pip for the project backend

## Code rules
1. Do not start the name of helper functions with an underscore. Eg. _helper_function() -> This is not acceptable.
2. Do not create docstrings at the top of the file (module docstrings) NOT NEEDED.
3. Do not create one liner docstrings or vague comments.
4. Create docstrings explaining the function/module along with params correctly.
5. Comments should be detailed and added to explain underlying functionality rather than stating the obvious.
6. Do not create multiple or not-needed helper functions that clutter the codebase.
7. Do not leave dead code or dead functions that are not used anywhere.
8. If a function is getting too big, modularize it and ensure that readability is always maintained.
9. Variables should never be camel cased. always underscore separated and should be meaningful.
10. Ensure that the functions are correctly typed and use pydantic for data validation.

## DB rules
1. Use mongodb async operations only using - motorasyncio
2. Ensure that the db is initialized once and used across to avoid connection overload.
3. DB performance should be a priority.
4. Ensure indexes are applied where necessary and explain why an entity should be indexed.
5. Use bulk operations and aggregations where applicable but not at the cost of complexity and readability.

## Error handling & Logging rules
1. Keep minimal try-catch blocks and make the code less bloated
2. If a flow is meant to fail - let it fail. D
o not fail-safe the flow by parsing errors. Fail the code so it can be identified and fixed
3. Use user-friendly and readable logs wherever necessary. Define a separate log file with a logger and use that logger across all application with default as info. 
4. Do not do over-logging. Log only the important things each flow to understand and aid in debugging
5. use HTTPException for expected error and respond with correct error codes.

## AI Integration Rules
1. We will be using Google ADK in this project. You are provided with a google-adk-python skill to refer in order to build AI Agents using Google ADK
2. We can utilize Google's SDK as well and you also have google-genai-sdk-python to support you on this. SDK can be used when ADK implementation is not possible or too complicated.
3. DO NOT expose API_KEYS or any sensitive information while building. Ensure they are accessed through env variables.

# General Rule while building backend
1. Ask clarifying questions if something is unclear
2. Do not assume anything
3. Do not write unsafe and vulnerable code.