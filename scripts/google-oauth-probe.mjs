const baseUrl = process.env.EASY_LIVE_URL || "https://easy.kuzuryu.ai";

function redactUrl(rawUrl) {
  const url = new URL(rawUrl);
  for (const key of ["client_id", "redirect_uri", "state"]) {
    if (url.searchParams.has(key)) {
      url.searchParams.set(key, "<redacted>");
    }
  }
  return url.toString();
}

function cookieHeader(response) {
  const cookies = response.headers.getSetCookie?.() || [response.headers.get("set-cookie")].filter(Boolean);
  return cookies.map((cookie) => cookie.split(";")[0]).join("; ");
}

const loginUrl = `${baseUrl}/accounts/google/login/`;
const getResponse = await fetch(loginUrl);
const html = await getResponse.text();
const cookie = cookieHeader(getResponse);
const csrfMatch = html.match(/name="csrfmiddlewaretoken" value="([^"]+)"/);

if (!csrfMatch) {
  throw new Error("Google login page did not include a CSRF token.");
}

const postResponse = await fetch(loginUrl, {
  method: "POST",
  redirect: "manual",
  headers: {
    "content-type": "application/x-www-form-urlencoded",
    cookie,
    referer: loginUrl,
  },
  body: new URLSearchParams({ csrfmiddlewaretoken: csrfMatch[1] }).toString(),
});

const location = postResponse.headers.get("location") || "";
let googleStatus = null;
let googleTitle = "";
let googleError = "";

if (location.startsWith("https://accounts.google.com/")) {
  const googleResponse = await fetch(location, { redirect: "manual" });
  googleStatus = googleResponse.status;
  const googleBody = await googleResponse.text();
  googleTitle = googleBody.match(/<title>([^<]+)<\/title>/i)?.[1] || "";
  googleError =
    googleBody.match(/Error\s+400:\s*([^<\n]+)/i)?.[1]?.trim() ||
    googleBody.match(/redirect_uri_mismatch/i)?.[0] ||
    "";
}

console.log(
  JSON.stringify(
    {
      status: postResponse.status,
      redirectsToGoogle: location.startsWith("https://accounts.google.com/"),
      location: location ? redactUrl(location) : "",
      googleStatus,
      googleTitle,
      googleError,
    },
    null,
    2,
  ),
);
