# YOKL ChatGPT cache trial — final readings

Five paid requests, no paid retries, five usable ranking results:

| Run | Evomi MB | Automatic successes | Additional delivered evidence |
| --- | ---: | ---: | --- |
| First keyword5221 | 1.493799 | 0 | One same-paid-answer screenshot recovered locally |
| Remaining5222–5225 | 3.422797 | 2 | Two original saved captures accepted after explicit review |
| Total | 4.916596 | 2 | Five delivered results in total |

Cost is **0.9833192 MB per delivered result**, not five automatic successes.
The raw CSVs and reports remain unchanged; recovery/review receipts identify the
exceptions and bind screenshots to their reviewed SHA256 hashes.

The first paid capture moved during screenshotting. Subsequent diagnosis found
subpixel compositor rounding rejected as movement (0.0084CSSpx); the ChatGPT-only
guard now tolerates at most1/16CSSpx, with unchanged answer text and full rank
visibility still required. The culinary keyword's screenshot passed capture/OCR
but the general business-name matcher rejected "Yokl Food Tours" against "Yokl,
Inc.". Official https://yokltours.com/ and https://yokltours.com/contact-us/ link
the food-tour brand to Hello@shopyokl.com. Root reviewed that exact saved capture;
no global name-matcher or backend alias changes were made.

Both meter runs completed the >=300s post-traffic window plus stable readings.
First balance29882.103466 ->29880.609667MB; follow-up ->29877.186870MB.
Both wrappers restored originalAPK79/accessibility/noVPN. Candidate84 was used
only on device104; other phones and daily defaults were unchanged.

These are warm-cache, city-first, one-device YOKL observations. Direct readiness
checks warmed resources outside Evomi. They are not a randomized cold-cache
comparison, fleet-wide reliability proof, or Copilot savings measurement.
The earlier interrupted mixed-platform YOKL run cost109.547768MB separately;
it must remain included in any full-project cost total.
