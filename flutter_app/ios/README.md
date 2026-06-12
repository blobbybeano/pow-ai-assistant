# iOS minimum deployment target

This project pins the iOS deployment target to **13.0** for every target and pod. Firebase's modern gRPC stack no longer supports iOS 12 when building for real devices, so lowering the target causes Xcode builds to fail with errors like `unsupported option '-G' for target 'arm64-apple-ios10.0'`.

To validate the settings after updating dependencies, run:

```
./ios/check_ios_target.sh
```

The script fails if the Podfile platform or any `IPHONEOS_DEPLOYMENT_TARGET` entries drop below 13.0, keeping the app buildable on hardware.
