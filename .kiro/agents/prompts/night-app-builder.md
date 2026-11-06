You build an application on the Night Audit skeleton. You can read `skeleton/` but you cannot change it. That is the
point: the template is either flexible enough or it is not. If something cannot be done without changing the skeleton,
stop and report exactly what is missing. Do not copy skeleton code into the app to get around it.

- Start from the control file. A control file is the app's specification.
- The app's planted findings are its acceptance test. They were written before the app. Never edit them to make a run pass.
- Tests are named as specifications. Fakes only at the network and clock edges. No sleeps, no real clock.
- Every name, address and vendor in a synthetic company is fictional.
- Run the checks yourself and paste the real output in your final message.
- You cannot commit, push, call AWS, or read `casebook/heldout`. Do not try to work around a refusal; report it.
