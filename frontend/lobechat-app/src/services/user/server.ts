import { lambdaClient } from '@/libs/trpc/client';
import { IUserService } from '@/services/user/type';
import { updateUserSettings as updateEtherionUserSettings } from '@/etherion/bridge/userSettings';

export class ServerService implements IUserService {
  getUserRegistrationDuration: IUserService['getUserRegistrationDuration'] = async () => {
    return lambdaClient.user.getUserRegistrationDuration.query();
  };

  getUserState: IUserService['getUserState'] = async () => {
    return lambdaClient.user.getUserState.query();
  };

  getUserSSOProviders: IUserService['getUserSSOProviders'] = async () => {
    return lambdaClient.user.getUserSSOProviders.query();
  };

  unlinkSSOProvider: IUserService['unlinkSSOProvider'] = async (
    provider: string,
    providerAccountId: string,
  ) => {
    return lambdaClient.user.unlinkSSOProvider.mutate({ provider, providerAccountId });
  };

  makeUserOnboarded = async () => {
    return lambdaClient.user.makeUserOnboarded.mutate();
  };

  updateAvatar: IUserService['updateAvatar'] = async (avatar) => {
    return lambdaClient.user.updateAvatar.mutate(avatar);
  };

  updatePreference: IUserService['updatePreference'] = async (preference) => {
    return lambdaClient.user.updatePreference.mutate(preference);
  };

  updateGuide: IUserService['updateGuide'] = async (guide) => {
    return lambdaClient.user.updateGuide.mutate(guide);
  };

  updateUserSettings: IUserService['updateUserSettings'] = async (value, signal) => {
    // Etherion: delegate user settings persistence to GraphQL bridge.
    // The bridge operates on a JSON patch object; abort signals are currently
    // not wired through Apollo, so we ignore the optional `signal` here.
    await updateEtherionUserSettings(value as any);
  };

  resetUserSettings: IUserService['resetUserSettings'] = async () => {
    // Etherion: no dedicated "reset to defaults" GraphQL operation exists yet.
    // Frontend callers that rely on reset semantics should be updated to send
    // explicit default settings via updateUserSettings once the backend API is
    // available. For now, this is a no-op to avoid calling the legacy Lambda
    // backend in the Etherion fork.
    return Promise.resolve();
  };
}
