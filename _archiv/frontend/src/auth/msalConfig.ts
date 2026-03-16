import { Configuration, LogLevel } from "@azure/msal-browser";

const clientId = import.meta.env.VITE_AZURE_CLIENT_ID as string;
const tenantId = import.meta.env.VITE_AZURE_TENANT_ID as string;
const domain = import.meta.env.VITE_DOMAIN as string;

export const msalConfig: Configuration = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: `https://${domain}/auth/callback`,
    postLogoutRedirectUri: `https://${domain}/`,
  },
  cache: {
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
    },
  },
};

export const loginRequest = {
  scopes: ["openid", "profile", "email", "User.Read"],
};
