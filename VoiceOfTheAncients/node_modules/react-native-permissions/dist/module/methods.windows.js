"use strict";

import { NativeModules } from 'react-native';
import { canScheduleExactAlarms, checkLocationAccuracy, openPhotoPicker, requestLocationAccuracy } from './unsupportedMethods';
import { uniq } from './utils';
const NativeModule = NativeModules.RNPermissions;
const openSettings = async () => {
  await NativeModule.OpenSettings();
};
const check = permission => {
  return NativeModule.Check(permission);
};
const request = permission => {
  return NativeModule.Request(permission);
};
const checkNotifications = async () => {
  const status = await NativeModule.CheckNotifications();
  return {
    status,
    settings: {}
  };
};
const checkMultiple = async permissions => {
  const output = {};
  for (const permission of uniq(permissions)) {
    output[permission] = await check(permission);
  }
  return output;
};
const requestMultiple = async permissions => {
  const output = {};
  for (const permission of uniq(permissions)) {
    output[permission] = await request(permission);
  }
  return output;
};
export const methods = {
  canScheduleExactAlarms,
  check,
  checkLocationAccuracy,
  checkMultiple,
  checkNotifications,
  openPhotoPicker,
  openSettings,
  request,
  requestLocationAccuracy,
  requestMultiple,
  requestNotifications: checkNotifications
};
//# sourceMappingURL=methods.windows.js.map