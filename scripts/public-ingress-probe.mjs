import { spawnSync } from "node:child_process";
import dgram from "node:dgram";

const hostname = process.env.EASY_HOSTNAME || "easy.kuzuryu.ai";
const expectedLanHost = process.env.EASY_INGRESS_LAN_HOST || "192.168.0.51";
const timeoutMs = Number(process.env.EASY_PROBE_TIMEOUT_MS || 5000);

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  return {
    status: result.status,
    stdout: (result.stdout || "").trim(),
    stderr: (result.stderr || "").trim(),
  };
}

function curlWanHealth(wanIp) {
  const result = run("curl.exe", [
    "-sS",
    "--connect-timeout",
    "5",
    "--resolve",
    `${hostname}:443:${wanIp}`,
    "-o",
    "NUL",
    "-w",
    "%{http_code} %{ssl_verify_result} %{remote_ip}",
    `https://${hostname}/health/`,
  ]);
  return {
    ok: result.status === 0 && result.stdout.startsWith("200 "),
    output: result.stdout || result.stderr,
  };
}

async function discoverGateway() {
  const message = Buffer.from(
    [
      "M-SEARCH * HTTP/1.1",
      "HOST: 239.255.255.250:1900",
      'MAN: "ssdp:discover"',
      "MX: 2",
      "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1",
      "",
      "",
    ].join("\r\n"),
  );

  const socket = dgram.createSocket("udp4");
  const responses = [];

  await new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, timeoutMs);
    socket.on("message", (data) => responses.push(data.toString("utf8")));
    socket.on("error", reject);
    socket.bind(() => socket.send(message, 1900, "239.255.255.250"));
    socket.on("close", () => clearTimeout(timer));
  }).finally(() => socket.close());

  const locations = [
    ...new Set(
      responses
        .map((response) => response.match(/^location:\s*(.+)$/im)?.[1]?.trim())
        .filter(Boolean),
    ),
  ];
  return locations;
}

function joinUrl(base, path) {
  return new URL(path, base).toString();
}

function textBetween(xml, tag) {
  return xml.match(new RegExp(`<${tag}>([^<]+)</${tag}>`, "i"))?.[1] || "";
}

async function findWanService(location) {
  const rootXml = await fetch(location).then((response) => response.text());
  const serviceMatch = rootXml.match(
    /<service>[\s\S]*?<serviceType>(urn:schemas-upnp-org:service:WAN(?:IP|PPP)Connection:\d+)<\/serviceType>[\s\S]*?<controlURL>([^<]+)<\/controlURL>[\s\S]*?<\/service>/i,
  );

  if (!serviceMatch) {
    return null;
  }

  return {
    serviceType: serviceMatch[1],
    controlUrl: joinUrl(location, serviceMatch[2]),
  };
}

async function soap(service, action, body) {
  const envelope = `<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:${action} xmlns:u="${service.serviceType}">${body}</u:${action}>
  </s:Body>
</s:Envelope>`;

  const response = await fetch(service.controlUrl, {
    method: "POST",
    headers: {
      "content-type": 'text/xml; charset="utf-8"',
      soapaction: `"${service.serviceType}#${action}"`,
    },
    body: envelope,
  });
  return {
    status: response.status,
    text: await response.text(),
  };
}

async function main() {
  const publicIp = await fetch("https://api.ipify.org").then((response) => response.text());
  const wanHealth = curlWanHealth(publicIp);
  const locations = await discoverGateway();
  const services = [];

  for (const location of locations) {
    try {
      const service = await findWanService(location);
      if (!service) continue;
      const externalIp = await soap(service, "GetExternalIPAddress", "");
      const mapping = await soap(
        service,
        "GetSpecificPortMappingEntry",
        "<NewRemoteHost></NewRemoteHost><NewExternalPort>443</NewExternalPort><NewProtocol>TCP</NewProtocol>",
      );
      services.push({
        location,
        serviceType: service.serviceType,
        controlUrl: service.controlUrl,
        externalIpStatus: externalIp.status,
        externalIp: textBetween(externalIp.text, "NewExternalIPAddress"),
        mappingStatus: mapping.status,
        mappingInternalClient: textBetween(mapping.text, "NewInternalClient"),
        mappingInternalPort: textBetween(mapping.text, "NewInternalPort"),
        mappingDescription: textBetween(mapping.text, "NewPortMappingDescription"),
        mapsExpectedHost:
          textBetween(mapping.text, "NewInternalClient") === expectedLanHost &&
          textBetween(mapping.text, "NewInternalPort") === "443",
      });
    } catch (error) {
      services.push({ location, error: error.message });
    }
  }

  console.log(
    JSON.stringify(
      {
        hostname,
        expectedLanHost,
        publicIp,
        wanHealth,
        upnpLocations: locations,
        upnpServices: services,
      },
      null,
      2,
    ),
  );
}

await main();
