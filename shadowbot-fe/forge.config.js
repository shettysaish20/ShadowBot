// Key issue faced for Windows: Electron fuses loading issue (fixed)
const { FusesPlugin } = require('@electron-forge/plugin-fuses');
const { FuseV1Options, FuseVersion } = require('@electron/fuses');
const path = require('path');

module.exports = {
    packagerConfig: {
        asar: true,
        extraResource: [path.join(__dirname, 'src/assets/SystemAudioDump')],
        executableName: 'ShadowBot',
        icon: 'src/assets/ShadowBot_logo',
        // use `security find-identity -v -p codesigning` to find your identity
        // for macos signing
        // also fuck apple
        // osxSign: {
        //    identity: '<paste your identity here>',
        //   optionsForFile: (filePath) => {
        //       return {
        //           entitlements: 'entitlements.plist',
        //       };
        //   },
        // },
        // notarize if off cuz i ran this for 6 hours and it still didnt finish
        // osxNotarize: {
        //    appleId: 'your apple id',
        //    appleIdPassword: 'app specific password',
        //    teamId: 'your team id',
        // }, // .ico for win, .icns for mac
    },
    rebuildConfig: {},
    makers: [
        {
            name: '@electron-forge/maker-squirrel',
            config: {
                name: 'shadowbot-fe',           // no spaces
                productName: 'ShadowBot',
                authors: 'Shadow AI, an incorporate of The School of AI EAG-V1',
                description: 'Shadow Bot - AI assistant for interviews and learning',
                setupExe: 'ShadowBotSetup.exe',
                exe: 'ShadowBot.exe',
                shortcutName: 'ShadowBot',
                setupIcon: 'src/assets/ShadowBot_logo.ico',
                createDesktopShortcut: true,
                createStartMenuShortcut: true
            }
        },
        {
            name: '@electron-forge/maker-dmg',
            platforms: ['darwin'],
            config: {
                name: 'ShadowBot',
                icon: 'src/assets/ShadowBot_logo.icns'
            }
        },
        {
            name: '@electron-forge/maker-zip',
            platforms: ['darwin', 'win32'],
        }
    ],
    plugins: [
        {
            name: '@electron-forge/plugin-auto-unpack-natives',
            config: {},
        },
        // Fuses are used to enable/disable various Electron functionality
        // at package time, before code signing the application
        new FusesPlugin({
            version: FuseVersion.V1,
            [FuseV1Options.RunAsNode]: false,
            [FuseV1Options.EnableCookieEncryption]: true,
            [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
            [FuseV1Options.EnableNodeCliInspectArguments]: false,
            [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: false, // Turned False for Windows application creation
            [FuseV1Options.OnlyLoadAppFromAsar]: true,
        }),
    ],
};
