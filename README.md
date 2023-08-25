# BSA Unit Tracker

Hi.  I'm a District Membership chair for the BSA.  So far (at least in my district), this has involved a lot of me doing stuff like sending mail-merge type emails.  Which is fine, if you have the tools to do this.  I had some hacky app script.  This will be better.

## How to run

### Main server

```
python main.py 
```

```
flask --app main run --port 8080
```

### Email Job

```
flask --app email_job send-email
```