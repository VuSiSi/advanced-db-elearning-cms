import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const TARGET_PATH = __ENV.TARGET_PATH || "/api/stress-test/";

export const allowedOrLimited = new Rate("allowed_or_limited");
export const rateLimited = new Rate("rate_limited");
export const rateLimitedResponses = new Counter("rate_limited_responses");

export const options = {
  scenarios: {
    rate_limit_probe: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 20),
      duration: __ENV.DURATION || "30s",
    },
  },
  thresholds: {
    allowed_or_limited: ["rate>0.99"],
    rate_limited: ["rate>0"],
    http_req_duration: ["p(95)<1000"],
  },
};

export default function () {
  const response = http.get(`${BASE_URL}${TARGET_PATH}`);
  const acceptedStatus = response.status === 200 || response.status === 429;
  const limited = response.status === 429;

  allowedOrLimited.add(acceptedStatus);
  rateLimited.add(limited);

  if (limited) {
    rateLimitedResponses.add(1);
  }

  check(response, {
    "request is accepted or rate-limited": () => acceptedStatus,
    "rate limit response is 429": () => !limited || response.status === 429,
  });

  sleep(Number(__ENV.SLEEP || 0.1));
}
