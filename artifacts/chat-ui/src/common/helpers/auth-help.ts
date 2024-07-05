import { getCurrentUser, fetchAuthSession } from 'aws-amplify/auth';

export abstract class AuthHelper {
    static async getUserDetails() {
        let output = await Promise.all([getCurrentUser(), fetchAuthSession()]).then((res) => {
            let merged = { ...res[0], ...res[1] };
            return merged;
        });
        return output;
    }
}