// Minimal EdgeConfig module to satisfy vendored featureFlags imports.
// Returns disabled so environment variable-based flags are used.
export class EdgeConfig {
  static isEnabled(): boolean {
    return false;
  }
  async getFeatureFlags(): Promise<Record<string, any> | null> {
    return null;
  }
}
