// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { CognitoIdentityProviderClient, InitiateAuthCommand, SignUpCommand, ConfirmSignUpCommand } from "@aws-sdk/client-cognito-identity-provider";
import { getRuntimeConfig } from "./runtime-config";

function getClient() {
  const config = getRuntimeConfig();
  return new CognitoIdentityProviderClient({ region: config.cognitoRegion });
}

export const signIn = async (username: string, password: string) => {
  const config = getRuntimeConfig();
  const params = {
    AuthFlow: "USER_PASSWORD_AUTH" as const,
    ClientId: config.cognitoClientId,
    AuthParameters: {
      USERNAME: username,
      PASSWORD: password,
    },
  };

  try {
    const command = new InitiateAuthCommand(params);
    const { AuthenticationResult } = await getClient().send(command);
    if (AuthenticationResult) {
      sessionStorage.setItem("idToken", AuthenticationResult.IdToken || '');
      sessionStorage.setItem("accessToken", AuthenticationResult.AccessToken || '');
      sessionStorage.setItem("refreshToken", AuthenticationResult.RefreshToken || '');
      return AuthenticationResult;
    }
  } catch (error) {
    console.error("Error signing in: ", error);
    throw error;
  }
};

export const signUp = async (email: string, password: string) => {
  const config = getRuntimeConfig();
  const params = {
    ClientId: config.cognitoClientId,
    Username: email,
    Password: password,
    UserAttributes: [
      {
        Name: "email",
        Value: email,
      },
    ],
  };
  try {
    const command = new SignUpCommand(params);
    const response = await getClient().send(command);
    console.log("Sign up success: ", response);
    return response;
  } catch (error) {
    console.error("Error signing up: ", error);
    throw error;
  }
};

export const confirmSignUp = async (username: string, code: string) => {
  const config = getRuntimeConfig();
  const params = {
    ClientId: config.cognitoClientId,
    Username: username,
    ConfirmationCode: code,
  };
  try {
    const command = new ConfirmSignUpCommand(params);
    await getClient().send(command);
    console.log("User confirmed successfully");
    return true;
  } catch (error) {
    console.error("Error confirming sign up: ", error);
    throw error;
  }
};
