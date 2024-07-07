export interface NavigationPanelState {
  collapsed?: boolean;
  collapsedSections?: Record<number, boolean>;
}

export interface AppPage {
  setAppData: any;
  manageDocument?: boolean;
}