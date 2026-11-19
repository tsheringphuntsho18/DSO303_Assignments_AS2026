// Cognito SRP sign-in (matches the app client config in infra/auth.tf,
// which only allows ALLOW_USER_SRP_AUTH — no plaintext password ever goes
// over the wire).
const { CognitoUserPool, CognitoUser, AuthenticationDetails } = AmazonCognitoIdentity;

const pool = new CognitoUserPool({
  UserPoolId: window.EDUEXAM_CONFIG.cognito.userPoolId,
  ClientId: window.EDUEXAM_CONFIG.cognito.clientId,
});

const Auth = {
  idToken: sessionStorage.getItem("eduexam_id_token") || null,
  groups: JSON.parse(sessionStorage.getItem("eduexam_groups") || "[]"),

  signIn(email, password) {
    return new Promise((resolve, reject) => {
      const user = new CognitoUser({ Username: email, Pool: pool });
      const details = new AuthenticationDetails({ Username: email, Password: password });
      user.authenticateUser(details, {
        onSuccess: (session) => {
          Auth.idToken = session.getIdToken().getJwtToken();
          Auth.groups = session.getIdToken().payload["cognito:groups"] || [];
          sessionStorage.setItem("eduexam_id_token", Auth.idToken);
          sessionStorage.setItem("eduexam_groups", JSON.stringify(Auth.groups));
          resolve(Auth);
        },
        onFailure: reject,
        mfaRequired: () => reject(new Error("MFA sign-in isn't implemented in this lightweight prototype")),
      });
    });
  },

  signOut() {
    sessionStorage.removeItem("eduexam_id_token");
    sessionStorage.removeItem("eduexam_groups");
    Auth.idToken = null;
    Auth.groups = [];
  },

  authHeader() {
    return Auth.idToken ? { Authorization: `Bearer ${Auth.idToken}` } : {};
  },
};
