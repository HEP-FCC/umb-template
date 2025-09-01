/**
 * This shim file is necessary to make TypeScript understand the structure of .vue files.
 * Without it, TypeScript will complain that it cannot find modules ending in .vue.
 * This file declares a module for all .vue files and types them as a Vue Component.
 */
declare module "*.vue" {
    import type { DefineComponent } from "vue";
    const component: DefineComponent<object, object, unknown>;
    export default component;
}
