# Health check & uptime monitoring

← Back to [README](../README.md)

This app exposes a **built-in HTTP health endpoint** — no application code is
required. You can point any external monitor at it. This guide covers the
endpoint and a lightweight, hourly **AWS** monitor that emails you when the app
is down.

## The health endpoint

Streamlit serves a health route at the app root. For the hosted demo:

| Endpoint | URL | Returns | Meaning |
|---|---|---|---|
| Server health | `https://rag-playground-prakosd.streamlit.app/_stcore/health` | `200` body `ok` | The Streamlit **server** is up and accepting connections. |
| Script health | `https://rag-playground-prakosd.streamlit.app/_stcore/script-health-check` | `200` `ok` / `503` `error` | Stricter — also verifies the app **script runs** without raising. |

Running locally (or in the dev container) the same paths are available on
`http://localhost:8501/_stcore/health`.

Use `/_stcore/health` for a simple "is it reachable" check. Use
`/_stcore/script-health-check` if you also want to catch a booting app that
serves pages but errors while rendering.

> **Community Cloud note:** the cloud host puts inactive apps to sleep. An hourly
> probe will generally keep the app **awake**. While an app is asleep or waking,
> the probe may be answered by the platform's wake-up page rather than the real
> runtime — factor that into how many consecutive failures should trigger an
> alert (see the retry setting below).

## Option A — EventBridge Scheduler → Lambda → SNS email (recommended)

A tiny, cheap serverless monitor: a schedule triggers a Lambda that does an
HTTPS `GET`; on failure it publishes to an SNS topic that emails you.

### 1. Create the SNS topic and email subscription

1. Open **Amazon SNS → Topics → Create topic**. Type **Standard**, name it
   e.g. `rag-playground-health-alerts`.
2. Open the topic → **Create subscription**. Protocol **Email**, endpoint your
   address. **Confirm** the subscription from the email AWS sends you.
3. Copy the topic **ARN** (e.g. `arn:aws:sns:ap-southeast-2:123456789012:rag-playground-health-alerts`).

### 2. Create the Lambda function

1. Open **AWS Lambda → Create function**. Author from scratch, runtime
   **Python 3.13**, name e.g. `rag-playground-health-check`.
2. Under **Configuration → Environment variables**, add:
   - `HEALTH_URL` = `https://rag-playground-prakosd.streamlit.app/_stcore/health`
   - `SNS_TOPIC_ARN` = the ARN from step 1.
3. Under **Configuration → Permissions**, open the function's execution role and
   attach an inline policy allowing `sns:Publish` to your topic ARN:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "sns:Publish", "Resource": "arn:aws:sns:ap-southeast-2:123456789012:rag-playground-health-alerts" }
     ]
   }
   ```

4. Paste this handler (standard library only — no dependencies to package):

   ```python
   import os
   import urllib.request

   import boto3  # provided by the Lambda Python runtime

   HEALTH_URL = os.environ["HEALTH_URL"]
   SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
   TIMEOUT_SECONDS = 10
   EXPECTED_BODY = "ok"


   def handler(event, context):
       try:
           with urllib.request.urlopen(HEALTH_URL, timeout=TIMEOUT_SECONDS) as resp:
               body = resp.read(64).decode("utf-8", "replace").strip().lower()
               healthy = resp.status == 200 and body == EXPECTED_BODY
               detail = f"HTTP {resp.status}, body={body!r}"
       except Exception as exc:  # network error, timeout, non-2xx, DNS, etc.
           healthy = False
           detail = f"{type(exc).__name__}: {exc}"

       if healthy:
           return {"healthy": True, "detail": detail}

       boto3.client("sns").publish(
           TopicArn=SNS_TOPIC_ARN,
           Subject="[rag-playground] health check FAILED",
           Message=f"Health check failed for {HEALTH_URL}\n\n{detail}",
       )
       return {"healthy": False, "detail": detail}
   ```

5. Set the handler to `lambda_function.handler` (match your file/function names)
   and raise the function **timeout** to ~15 seconds (Configuration → General
   configuration) so the HTTP request has room to complete.

### 3. Schedule it hourly with EventBridge Scheduler

1. Open **Amazon EventBridge → Scheduler → Schedules → Create schedule**.
2. **Recurring schedule**, rate expression `rate(1 hour)`. (Flexible time window:
   **Off**.)
3. Target **AWS Lambda → Invoke**, pick the `rag-playground-health-check`
   function. Payload can be empty (`{}`).
4. Let the console create/choose an execution role that can invoke the Lambda.
   **Create schedule**.

That's it — you'll get an email within the hour whenever a probe fails.

### Reduce false alarms (optional)

A single failed probe can be a transient blip or a cold-start wake-up. To alert
only on **sustained** downtime, either:

- have the Lambda retry 2–3 times with a short sleep before publishing, or
- write each result to a CloudWatch **custom metric** and alarm on
  "N datapoints below threshold" instead of emailing from the Lambda directly.

## Option B — CloudWatch Synthetics canary (AWS-native, more features)

If you prefer a managed HTTP check with built-in history and screenshots:

1. **CloudWatch → Application Signals / Synthetics → Create canary**, blueprint
   **Heartbeat monitoring**, endpoint the `/_stcore/health` URL, schedule every
   hour.
2. The canary emits a `SuccessPercent` metric. Create a **CloudWatch alarm** on
   it (e.g. `< 100` for 1 period) with an **SNS action** to the email topic from
   Option A.

This costs a little more than Option A but gives you dashboards and run history
without writing the probe yourself.

## Verifying the endpoint by hand

```bash
curl -i https://rag-playground-prakosd.streamlit.app/_stcore/health
# → HTTP/2 200 ... \n ok
```

A `200` with body `ok` means healthy; a timeout, connection error, or non-`200`
means the alert should fire.
