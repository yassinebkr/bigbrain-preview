import {
  require_react_dom
} from "./chunk-HAWPO343.js";
import {
  require_jsx_runtime
} from "./chunk-SO5E4B4S.js";
import {
  require_react
} from "./chunk-FLFXNC7H.js";
import {
  __privateAdd,
  __privateGet,
  __privateSet,
  __toESM
} from "./chunk-NGNPUD5H.js";

// node_modules/@radix-ui/react-context/dist/index.mjs
var React = __toESM(require_react(), 1);
var import_jsx_runtime = __toESM(require_jsx_runtime(), 1);
var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });
function createContext2(rootComponentName, defaultContext) {
  const Context = React.createContext(defaultContext);
  Context.displayName = rootComponentName + "Context";
  const Provider = __name((props) => {
    const { children, ...context } = props;
    const value = React.useMemo(() => context, Object.values(context));
    return (0, import_jsx_runtime.jsx)(Context.Provider, { value, children });
  }, "Provider");
  Provider.displayName = rootComponentName + "Provider";
  function useContext22(consumerName, options = {}) {
    const { optional = false } = options;
    const context = React.useContext(Context);
    if (context) return context;
    if (defaultContext !== void 0) return defaultContext;
    if (optional) return void 0;
    throw new Error(`\`${consumerName}\` must be used within \`${rootComponentName}\``);
  }
  __name(useContext22, "useContext");
  return [Provider, useContext22];
}
__name(createContext2, "createContext");
function createContextScope(scopeName, createContextScopeDeps = []) {
  let defaultContexts = [];
  function createContext32(rootComponentName, defaultContext) {
    const BaseContext = React.createContext(defaultContext);
    BaseContext.displayName = rootComponentName + "Context";
    const index = defaultContexts.length;
    defaultContexts = [...defaultContexts, defaultContext];
    const Provider = __name((props) => {
      const { scope, children, ...context } = props;
      const Context = scope?.[scopeName]?.[index] || BaseContext;
      const value = React.useMemo(() => context, Object.values(context));
      return (0, import_jsx_runtime.jsx)(Context.Provider, { value, children });
    }, "Provider");
    Provider.displayName = rootComponentName + "Provider";
    function useContext22(consumerName, scope, options = {}) {
      const { optional = false } = options;
      const Context = scope?.[scopeName]?.[index] || BaseContext;
      const context = React.useContext(Context);
      if (context) return context;
      if (defaultContext !== void 0) return defaultContext;
      if (optional) return void 0;
      throw new Error(`\`${consumerName}\` must be used within \`${rootComponentName}\``);
    }
    __name(useContext22, "useContext");
    return [Provider, useContext22];
  }
  __name(createContext32, "createContext");
  const createScope = __name(() => {
    const scopeContexts = defaultContexts.map((defaultContext) => {
      return React.createContext(defaultContext);
    });
    return __name(function useScope(scope) {
      const contexts = scope?.[scopeName] || scopeContexts;
      return React.useMemo(
        () => ({ [`__scope${scopeName}`]: { ...scope, [scopeName]: contexts } }),
        [scope, contexts]
      );
    }, "useScope");
  }, "createScope");
  createScope.scopeName = scopeName;
  return [createContext32, composeContextScopes(createScope, ...createContextScopeDeps)];
}
__name(createContextScope, "createContextScope");
function composeContextScopes(...scopes) {
  const baseScope = scopes[0];
  if (scopes.length === 1) return baseScope;
  const createScope = __name(() => {
    const scopeHooks = scopes.map((createScope2) => ({
      useScope: createScope2(),
      scopeName: createScope2.scopeName
    }));
    return __name(function useComposedScopes(overrideScopes) {
      const nextScopes = scopeHooks.reduce((nextScopes2, { useScope, scopeName }) => {
        const scopeProps = useScope(overrideScopes);
        const currentScope = scopeProps[`__scope${scopeName}`];
        return { ...nextScopes2, ...currentScope };
      }, {});
      return React.useMemo(() => ({ [`__scope${baseScope.scopeName}`]: nextScopes }), [nextScopes]);
    }, "useComposedScopes");
  }, "createScope");
  createScope.scopeName = baseScope.scopeName;
  return createScope;
}
__name(composeContextScopes, "composeContextScopes");

// node_modules/@radix-ui/react-compose-refs/dist/index.mjs
var React2 = __toESM(require_react(), 1);
var __defProp2 = Object.defineProperty;
var __name2 = (target, value) => __defProp2(target, "name", { value, configurable: true });
function setRef(ref, value) {
  if (typeof ref === "function") {
    return ref(value);
  } else if (ref !== null && ref !== void 0) {
    ref.current = value;
  }
}
__name2(setRef, "setRef");
function composeRefs(...refs) {
  return (node) => {
    let hasCleanup = false;
    const cleanups = refs.map((ref) => {
      const cleanup = setRef(ref, node);
      if (!hasCleanup && typeof cleanup == "function") {
        hasCleanup = true;
      }
      return cleanup;
    });
    if (hasCleanup) {
      return () => {
        for (let i = 0; i < cleanups.length; i++) {
          const cleanup = cleanups[i];
          if (typeof cleanup == "function") {
            cleanup();
          } else {
            setRef(refs[i], null);
          }
        }
      };
    }
  };
}
__name2(composeRefs, "composeRefs");
function useComposedRefs(...refs) {
  return React2.useCallback(composeRefs(...refs), refs);
}
__name2(useComposedRefs, "useComposedRefs");

// node_modules/@radix-ui/react-collection/dist/index.mjs
var React5 = __toESM(require_react(), 1);

// node_modules/@radix-ui/react-slot/dist/index.mjs
var React3 = __toESM(require_react(), 1);
var __defProp3 = Object.defineProperty;
var __name3 = (target, value) => __defProp3(target, "name", { value, configurable: true });
function createSlot(ownerName) {
  const Slot2 = React3.forwardRef((props, forwardedRef) => {
    let { children, ...slotProps } = props;
    let slottableElement = null;
    let hasSlottable = false;
    const newChildren = [];
    children = useUnwrappedLazy(children);
    React3.Children.forEach(children, (maybeSlottable) => {
      if (isSlottable(maybeSlottable)) {
        hasSlottable = true;
        const slottable = maybeSlottable;
        let child = "child" in slottable.props ? slottable.props.child : slottable.props.children;
        while (isLazyComponent(child) && typeof use === "function") {
          child = use(child._payload);
        }
        slottableElement = getSlottableElementFromSlottable(slottable, child);
        newChildren.push(slottableElement?.props?.children);
      } else {
        newChildren.push(maybeSlottable);
      }
    });
    if (slottableElement) {
      slottableElement = React3.cloneElement(slottableElement, void 0, newChildren);
    } else if (
      // A `Slottable` was found but it didn't resolve to a single element (e.g.
      // it wrapped multiple elements, text, or a render-prop `child` that
      // wasn't an element). Don't fall back to treating the `Slottable` wrapper
      // itself as the slot target — throw a descriptive error below instead.
      !hasSlottable && React3.Children.count(children) === 1 && React3.isValidElement(children)
    ) {
      slottableElement = children;
    }
    const slottableElementRef = slottableElement ? getElementRef(slottableElement) : void 0;
    const composedRef = useComposedRefs(forwardedRef, slottableElementRef);
    if (!slottableElement) {
      if (children || children === 0) {
        throw new Error(
          hasSlottable ? createSlottableError(ownerName) : createSlotError(ownerName)
        );
      }
      return children;
    }
    const mergedProps = mergeProps(slotProps, slottableElement.props ?? {});
    if (slottableElement.type !== React3.Fragment) {
      mergedProps.ref = forwardedRef ? composedRef : slottableElementRef;
    }
    return React3.cloneElement(slottableElement, mergedProps);
  });
  Slot2.displayName = `${ownerName}.Slot`;
  return Slot2;
}
__name3(createSlot, "createSlot");
var Slot = createSlot("Slot");
var SLOTTABLE_IDENTIFIER = /* @__PURE__ */ Symbol.for("radix.slottable");
function createSlottable(ownerName) {
  const Slottable2 = __name3((props) => "child" in props ? props.children(props.child) : props.children, "Slottable");
  Slottable2.displayName = `${ownerName}.Slottable`;
  Slottable2.__radixId = SLOTTABLE_IDENTIFIER;
  return Slottable2;
}
__name3(createSlottable, "createSlottable");
var Slottable = createSlottable("Slottable");
var getSlottableElementFromSlottable = __name3((slottable, child) => {
  if ("child" in slottable.props) {
    if (!React3.isValidElement(child)) return null;
    return React3.cloneElement(child, void 0, slottable.props.children(child.props.children));
  }
  return React3.isValidElement(child) ? child : null;
}, "getSlottableElementFromSlottable");
function mergeProps(slotProps, childProps) {
  const overrideProps = { ...childProps };
  for (const propName in childProps) {
    const slotPropValue = slotProps[propName];
    const childPropValue = childProps[propName];
    const isHandler = /^on[A-Z]/.test(propName);
    if (isHandler) {
      if (slotPropValue && childPropValue) {
        overrideProps[propName] = (...args) => {
          const result = childPropValue(...args);
          slotPropValue(...args);
          return result;
        };
      } else if (slotPropValue) {
        overrideProps[propName] = slotPropValue;
      }
    } else if (propName === "style") {
      overrideProps[propName] = { ...slotPropValue, ...childPropValue };
    } else if (propName === "className") {
      overrideProps[propName] = [slotPropValue, childPropValue].filter(Boolean).join(" ");
    } else if (propName === "aria-describedby") {
      overrideProps[propName] = concatAriaDescribedby(childPropValue, slotPropValue);
    }
  }
  return { ...slotProps, ...overrideProps };
}
__name3(mergeProps, "mergeProps");
function getElementRef(element) {
  let getter = Object.getOwnPropertyDescriptor(element.props, "ref")?.get;
  let mayWarn = getter && "isReactWarning" in getter && getter.isReactWarning;
  if (mayWarn) {
    return element.ref;
  }
  getter = Object.getOwnPropertyDescriptor(element, "ref")?.get;
  mayWarn = getter && "isReactWarning" in getter && getter.isReactWarning;
  if (mayWarn) {
    return element.props.ref;
  }
  return element.props.ref || element.ref;
}
__name3(getElementRef, "getElementRef");
function isSlottable(child) {
  return React3.isValidElement(child) && typeof child.type === "function" && "__radixId" in child.type && child.type.__radixId === SLOTTABLE_IDENTIFIER;
}
__name3(isSlottable, "isSlottable");
var REACT_LAZY_TYPE = /* @__PURE__ */ Symbol.for("react.lazy");
function isLazyComponent(element) {
  return element != null && typeof element === "object" && "$$typeof" in element && element.$$typeof === REACT_LAZY_TYPE && "_payload" in element && isPromiseLike(element._payload);
}
__name3(isLazyComponent, "isLazyComponent");
function isPromiseLike(value) {
  return typeof value === "object" && value !== null && "then" in value;
}
__name3(isPromiseLike, "isPromiseLike");
function useUnwrappedLazy(value) {
  let unwrapped = value;
  while (isLazyComponent(unwrapped) && typeof use === "function") {
    unwrapped = use(unwrapped._payload);
  }
  return unwrapped;
}
__name3(useUnwrappedLazy, "useUnwrappedLazy");
function concatAriaDescribedby(...values) {
  const ids = /* @__PURE__ */ new Set();
  for (const value of values) {
    if (typeof value !== "string") continue;
    for (const id of String(value).trim().split(/\s+/)) {
      if (id) ids.add(id);
    }
  }
  return ids.size > 0 ? Array.from(ids).join(" ") : void 0;
}
__name3(concatAriaDescribedby, "concatAriaDescribedby");
var createSlotError = __name3((ownerName) => {
  return `${ownerName} failed to slot onto its children. Expected a single React element child or \`Slottable\`.`;
}, "createSlotError");
var createSlottableError = __name3((ownerName) => {
  return `${ownerName} failed to slot onto its \`Slottable\`. Expected \`Slottable\` to receive a single React element child.`;
}, "createSlottableError");
var use = React3[" use ".trim().toString()];

// node_modules/@radix-ui/react-collection/dist/index.mjs
var import_jsx_runtime2 = __toESM(require_jsx_runtime(), 1);
var React22 = __toESM(require_react(), 1);

// node_modules/@radix-ui/react-use-layout-effect/dist/index.mjs
var React4 = __toESM(require_react(), 1);
var useLayoutEffect2 = globalThis?.document ? React4.useLayoutEffect : () => {
};

// node_modules/@radix-ui/react-collection/dist/index.mjs
var import_jsx_runtime3 = __toESM(require_jsx_runtime(), 1);
var __defProp4 = Object.defineProperty;
var __name4 = (target, value) => __defProp4(target, "name", { value, configurable: true });
function createCollection(name) {
  const PROVIDER_NAME = name + "CollectionProvider";
  const [createCollectionContext, createCollectionScope] = createContextScope(PROVIDER_NAME);
  const [CollectionProviderImpl, useCollectionContext] = createCollectionContext(
    PROVIDER_NAME,
    { collectionRef: { current: null }, itemMap: /* @__PURE__ */ new Map() }
  );
  const CollectionProvider = __name4((props) => {
    const { scope, children } = props;
    const ref = React5.useRef(null);
    const itemMap = React5.useRef(/* @__PURE__ */ new Map()).current;
    return (0, import_jsx_runtime2.jsx)(CollectionProviderImpl, { scope, itemMap, collectionRef: ref, children });
  }, "CollectionProvider");
  CollectionProvider.displayName = PROVIDER_NAME;
  const COLLECTION_SLOT_NAME = name + "CollectionSlot";
  const CollectionSlotImpl = createSlot(COLLECTION_SLOT_NAME);
  const CollectionSlot = React5.forwardRef(
    (props, forwardedRef) => {
      const { scope, children } = props;
      const context = useCollectionContext(COLLECTION_SLOT_NAME, scope);
      const composedRefs = useComposedRefs(forwardedRef, context.collectionRef);
      return (0, import_jsx_runtime2.jsx)(CollectionSlotImpl, { ref: composedRefs, children });
    }
  );
  CollectionSlot.displayName = COLLECTION_SLOT_NAME;
  const ITEM_SLOT_NAME = name + "CollectionItemSlot";
  const ITEM_DATA_ATTR = "data-radix-collection-item";
  const CollectionItemSlotImpl = createSlot(ITEM_SLOT_NAME);
  const CollectionItemSlot = React5.forwardRef(
    (props, forwardedRef) => {
      const { scope, children, ...itemData } = props;
      const ref = React5.useRef(null);
      const composedRefs = useComposedRefs(forwardedRef, ref);
      const context = useCollectionContext(ITEM_SLOT_NAME, scope);
      React5.useEffect(() => {
        context.itemMap.set(ref, { ref, ...itemData });
        return () => void context.itemMap.delete(ref);
      });
      return (0, import_jsx_runtime2.jsx)(CollectionItemSlotImpl, { ...{ [ITEM_DATA_ATTR]: "" }, ref: composedRefs, children });
    }
  );
  CollectionItemSlot.displayName = ITEM_SLOT_NAME;
  function useCollection(scope) {
    const context = useCollectionContext(name + "CollectionConsumer", scope);
    const getItems = React5.useCallback(() => {
      const collectionNode = context.collectionRef.current;
      if (!collectionNode) return [];
      const orderedNodes = Array.from(collectionNode.querySelectorAll(`[${ITEM_DATA_ATTR}]`));
      const items = Array.from(context.itemMap.values());
      const orderedItems = items.sort(
        (a, b) => orderedNodes.indexOf(a.ref.current) - orderedNodes.indexOf(b.ref.current)
      );
      return orderedItems;
    }, [context.collectionRef, context.itemMap]);
    return getItems;
  }
  __name4(useCollection, "useCollection");
  return [
    { Provider: CollectionProvider, Slot: CollectionSlot, ItemSlot: CollectionItemSlot },
    useCollection,
    createCollectionScope
  ];
}
__name4(createCollection, "createCollection");
var __instanciated = /* @__PURE__ */ new WeakMap();
var _keys, _a;
var OrderedDict = (_a = class extends Map {
  constructor(entries) {
    super(entries);
    __privateAdd(this, _keys);
    __privateSet(this, _keys, [...super.keys()]);
    __instanciated.set(this, true);
  }
  set(key, value) {
    if (__instanciated.get(this) && !this.has(key)) {
      __privateGet(this, _keys).push(key);
    }
    super.set(key, value);
    return this;
  }
  /**
   * Sets a key-value pair so that it ends up at the given index.
   * - Existing keys are moved
   * - Negative indices count from the end of the resulting dictionary, so
   *   inserting at -1 makes the item the last one, -2 the second to last, etc.
   * - Out-of-range indices are clamped
   */
  insert(index, key, value) {
    const has = this.has(key);
    const finalSize = has ? this.size : this.size + 1;
    const relativeIndex = toSafeInteger(index);
    const targetIndex = relativeIndex >= 0 ? Math.min(relativeIndex, finalSize - 1) : Math.max(finalSize + relativeIndex, 0);
    if (has ? __privateGet(this, _keys).indexOf(key) === targetIndex : targetIndex === this.size) {
      this.set(key, value);
      return this;
    }
    const keys = __privateGet(this, _keys).filter((existingKey) => existingKey !== key);
    keys.splice(targetIndex, 0, key);
    const entries = keys.map((entryKey) => [
      entryKey,
      entryKey === key ? value : this.get(entryKey)
    ]);
    this.clear();
    for (const [entryKey, entryValue] of entries) {
      this.set(entryKey, entryValue);
    }
    return this;
  }
  with(index, key, value) {
    const copy = new _a(this);
    copy.insert(index, key, value);
    return copy;
  }
  before(key) {
    const index = __privateGet(this, _keys).indexOf(key) - 1;
    if (index < 0) {
      return void 0;
    }
    return this.entryAt(index);
  }
  /**
   * Sets a new key-value pair at the position before the given key.
   */
  setBefore(key, newKey, value) {
    const index = __privateGet(this, _keys).indexOf(key);
    if (index === -1) {
      return this;
    }
    const currentIndex = __privateGet(this, _keys).indexOf(newKey);
    const targetIndex = currentIndex !== -1 && currentIndex < index ? index - 1 : index;
    return this.insert(targetIndex, newKey, value);
  }
  after(key) {
    let index = __privateGet(this, _keys).indexOf(key);
    index = index === -1 || index === this.size - 1 ? -1 : index + 1;
    if (index === -1) {
      return void 0;
    }
    return this.entryAt(index);
  }
  /**
   * Sets a new key-value pair at the position after the given key.
   */
  setAfter(key, newKey, value) {
    const index = __privateGet(this, _keys).indexOf(key);
    if (index === -1) {
      return this;
    }
    const currentIndex = __privateGet(this, _keys).indexOf(newKey);
    const targetIndex = currentIndex !== -1 && currentIndex <= index ? index : index + 1;
    return this.insert(targetIndex, newKey, value);
  }
  first() {
    return this.entryAt(0);
  }
  last() {
    return this.entryAt(-1);
  }
  clear() {
    __privateSet(this, _keys, []);
    return super.clear();
  }
  delete(key) {
    const deleted = super.delete(key);
    if (deleted) {
      __privateGet(this, _keys).splice(__privateGet(this, _keys).indexOf(key), 1);
    }
    return deleted;
  }
  deleteAt(index) {
    const key = this.keyAt(index);
    if (key !== void 0) {
      return this.delete(key);
    }
    return false;
  }
  at(index) {
    const key = at(__privateGet(this, _keys), index);
    if (key !== void 0) {
      return this.get(key);
    }
  }
  entryAt(index) {
    const key = at(__privateGet(this, _keys), index);
    if (key !== void 0) {
      return [key, this.get(key)];
    }
  }
  indexOf(key) {
    return __privateGet(this, _keys).indexOf(key);
  }
  keyAt(index) {
    return at(__privateGet(this, _keys), index);
  }
  from(key, offset) {
    const index = this.indexOf(key);
    if (index === -1) {
      return void 0;
    }
    let dest = index + offset;
    if (dest < 0) dest = 0;
    if (dest >= this.size) dest = this.size - 1;
    return this.at(dest);
  }
  keyFrom(key, offset) {
    const index = this.indexOf(key);
    if (index === -1) {
      return void 0;
    }
    let dest = index + offset;
    if (dest < 0) dest = 0;
    if (dest >= this.size) dest = this.size - 1;
    return this.keyAt(dest);
  }
  find(predicate, thisArg) {
    let index = 0;
    for (const entry of this) {
      if (Reflect.apply(predicate, thisArg, [entry, index, this])) {
        return entry;
      }
      index++;
    }
    return void 0;
  }
  findIndex(predicate, thisArg) {
    let index = 0;
    for (const entry of this) {
      if (Reflect.apply(predicate, thisArg, [entry, index, this])) {
        return index;
      }
      index++;
    }
    return -1;
  }
  filter(predicate, thisArg) {
    const entries = [];
    let index = 0;
    for (const entry of this) {
      if (Reflect.apply(predicate, thisArg, [entry, index, this])) {
        entries.push(entry);
      }
      index++;
    }
    return new _a(entries);
  }
  map(callbackfn, thisArg) {
    const entries = [];
    let index = 0;
    for (const entry of this) {
      entries.push([entry[0], Reflect.apply(callbackfn, thisArg, [entry, index, this])]);
      index++;
    }
    return new _a(entries);
  }
  reduce(...args) {
    const [callbackfn, initialValue] = args;
    const hasInitialValue = args.length > 1;
    if (!hasInitialValue && this.size === 0) {
      throw new TypeError("Reduce of empty OrderedDict with no initial value");
    }
    let index = 0;
    let accumulator = initialValue;
    for (const entry of this) {
      if (index === 0 && !hasInitialValue) {
        accumulator = entry;
      } else {
        accumulator = Reflect.apply(callbackfn, this, [accumulator, entry, index, this]);
      }
      index++;
    }
    return accumulator;
  }
  reduceRight(...args) {
    const [callbackfn, initialValue] = args;
    const hasInitialValue = args.length > 1;
    if (!hasInitialValue && this.size === 0) {
      throw new TypeError("Reduce of empty OrderedDict with no initial value");
    }
    let accumulator = initialValue;
    for (let index = this.size - 1; index >= 0; index--) {
      const entry = this.entryAt(index);
      if (index === this.size - 1 && !hasInitialValue) {
        accumulator = entry;
      } else {
        accumulator = Reflect.apply(callbackfn, this, [accumulator, entry, index, this]);
      }
    }
    return accumulator;
  }
  /**
   * Sorts the dictionary in place. This method mutates the dictionary and
   * returns a reference to the same object
   *
   * @param compareFn Function used to determine the order of the elements. It
   * is expected to return a negative value if the first argument is less than
   * the second argument, zero if they're equal, and a positive value otherwise.
   */
  sort(compareFn) {
    if (typeof compareFn !== "function") {
      throw new TypeError(`OrderedDict.sort requires a compare function`);
    }
    const entries = [...this.entries()].sort(compareFn);
    this.clear();
    for (const [key, value] of entries) {
      this.set(key, value);
    }
    return this;
  }
  /**
   * Returns a copy of the dictionary with its elements sorted.
   *
   * @param compareFn Function used to determine the order of the elements. It
   * is expected to return a negative value if the first argument is less than
   * the second argument, zero if they're equal, and a positive value otherwise.
   */
  toSorted(compareFn) {
    if (typeof compareFn !== "function") {
      throw new TypeError(`OrderedDict.toSorted requires a compare function`);
    }
    const entries = [...this.entries()].sort(compareFn);
    return new _a(entries);
  }
  toReversed() {
    const reversed = new _a();
    for (let index = this.size - 1; index >= 0; index--) {
      const key = this.keyAt(index);
      const element = this.get(key);
      reversed.set(key, element);
    }
    return reversed;
  }
  toSpliced(...args) {
    const entries = [...this.entries()];
    entries.splice(...args);
    return new _a(entries);
  }
  slice(start, end) {
    const result = new _a();
    for (const key of __privateGet(this, _keys).slice(start, end)) {
      result.set(key, this.get(key));
    }
    return result;
  }
  every(predicate, thisArg) {
    let index = 0;
    for (const entry of this) {
      if (!Reflect.apply(predicate, thisArg, [entry, index, this])) {
        return false;
      }
      index++;
    }
    return true;
  }
  some(predicate, thisArg) {
    let index = 0;
    for (const entry of this) {
      if (Reflect.apply(predicate, thisArg, [entry, index, this])) {
        return true;
      }
      index++;
    }
    return false;
  }
}, _keys = new WeakMap(), __name4(_a, "OrderedDict"), _a);
function at(array, index) {
  if ("at" in Array.prototype) {
    return Array.prototype.at.call(array, index);
  }
  const actualIndex = toSafeIndex(array, index);
  return actualIndex === -1 ? void 0 : array[actualIndex];
}
__name4(at, "at");
function toSafeIndex(array, index) {
  const length = array.length;
  const relativeIndex = toSafeInteger(index);
  const actualIndex = relativeIndex >= 0 ? relativeIndex : length + relativeIndex;
  return actualIndex < 0 || actualIndex >= length ? -1 : actualIndex;
}
__name4(toSafeIndex, "toSafeIndex");
function toSafeInteger(number) {
  return number !== number || number === 0 ? 0 : Math.trunc(number);
}
__name4(toSafeInteger, "toSafeInteger");
function createCollection2(name) {
  const PROVIDER_NAME = name + "CollectionProvider";
  const [createCollectionContext, createCollectionScope] = createContextScope(PROVIDER_NAME);
  const [CollectionStableContextProvider, useStableCollectionContext] = createCollectionContext(PROVIDER_NAME);
  CollectionStableContextProvider.displayName = name + "CollectionStableContextProvider";
  const [CollectionStatefulContextProvider, useStatefulCollectionContext] = createCollectionContext(PROVIDER_NAME);
  CollectionStatefulContextProvider.displayName = name + "CollectionStatefulContextProvider";
  const CollectionProvider = __name4(({ state, ...props }) => {
    return state ? (0, import_jsx_runtime3.jsx)(CollectionProviderImpl, { ...props, state }) : (0, import_jsx_runtime3.jsx)(CollectionInit, { ...props });
  }, "CollectionProvider");
  CollectionProvider.displayName = PROVIDER_NAME;
  const CollectionInit = __name4((props) => {
    const state = useInitCollection();
    return (0, import_jsx_runtime3.jsx)(CollectionProviderImpl, { ...props, state });
  }, "CollectionInit");
  CollectionInit.displayName = name + "CollectionInit";
  const CollectionProviderImpl = __name4((props) => {
    const { scope, children, state } = props;
    const ref = React22.useRef(null);
    const [collectionElement, setCollectionElement] = React22.useState(
      null
    );
    const composeRefs2 = useComposedRefs(ref, setCollectionElement);
    const [collection, setCollection] = state;
    const registryRef = React22.useRef(
      new OrderedDict()
    );
    const getCollection = React22.useCallback(() => {
      const registry = registryRef.current;
      if (!isInDocumentOrder(registry)) {
        registry.sort(sortByDocumentPosition);
      }
      return registry;
    }, []);
    React22.useEffect(() => {
      if (!collectionElement) {
        return;
      }
      const observer = getChildListObserver(() => {
        setCollection((map) => {
          const sorted = map.toSorted(sortByDocumentPosition);
          const orderChanged = sorted.some(([key], index) => map.keyAt(index) !== key);
          return orderChanged ? sorted : map;
        });
      });
      observer.observe(collectionElement, {
        childList: true,
        subtree: true
      });
      return () => {
        observer.disconnect();
      };
    }, [collectionElement, setCollection]);
    return (0, import_jsx_runtime3.jsx)(
      CollectionStableContextProvider,
      {
        scope,
        collectionElementRef: composeRefs2,
        collectionElementRefObject: ref,
        getCollection,
        setCollection,
        registryRef,
        children: (0, import_jsx_runtime3.jsx)(
          CollectionStatefulContextProvider,
          {
            scope,
            collectionElement,
            collection,
            children
          }
        )
      }
    );
  }, "CollectionProviderImpl");
  CollectionProviderImpl.displayName = name + "CollectionProviderImpl";
  const COLLECTION_SLOT_NAME = name + "CollectionSlot";
  const CollectionSlotImpl = createSlot(COLLECTION_SLOT_NAME);
  const CollectionSlot = React22.forwardRef(
    (props, forwardedRef) => {
      const { scope, children } = props;
      const context = useStableCollectionContext(COLLECTION_SLOT_NAME, scope);
      const composedRefs = useComposedRefs(forwardedRef, context.collectionElementRef);
      return (0, import_jsx_runtime3.jsx)(CollectionSlotImpl, { ref: composedRefs, children });
    }
  );
  CollectionSlot.displayName = COLLECTION_SLOT_NAME;
  const ITEM_SLOT_NAME = name + "CollectionItemSlot";
  const ITEM_DATA_ATTR = "data-radix-collection-item";
  const CollectionItemSlotImpl = createSlot(ITEM_SLOT_NAME);
  const CollectionItemSlot = React22.forwardRef(
    (props, forwardedRef) => {
      const { scope, children, ...itemData } = props;
      const ref = React22.useRef(null);
      const context = useStableCollectionContext(ITEM_SLOT_NAME, scope);
      const { setCollection, registryRef } = context;
      const itemDataRef = React22.useRef(itemData);
      if (!shallowEqual(itemDataRef.current, itemData)) {
        itemDataRef.current = itemData;
      }
      const memoizedItemData = itemDataRef.current;
      const registerElement = React22.useCallback(
        (node) => {
          const registry = registryRef.current;
          if (node) {
            registry.set(node, {
              ...itemDataRef.current,
              element: node
            });
          } else if (ref.current) {
            registry.delete(ref.current);
          }
        },
        [registryRef]
      );
      const composedRefs = useComposedRefs(forwardedRef, registerElement, ref);
      useLayoutEffect2(() => {
        const node = ref.current;
        const registry = registryRef.current;
        if (node && registry.has(node)) {
          registry.set(node, { ...memoizedItemData, element: node });
        }
      }, [memoizedItemData, registryRef]);
      const registeredRef = React22.useRef(null);
      React22.useEffect(() => {
        const element = ref.current;
        const registered = registeredRef.current;
        if ((registered?.element ?? null) === element && (!element || registered?.itemData === memoizedItemData)) {
          return;
        }
        registeredRef.current = element ? { element, itemData: memoizedItemData } : null;
        setCollection((map) => {
          const next = new OrderedDict(map);
          if (registered && registered.element !== element) {
            next.delete(registered.element);
          }
          if (element) {
            next.set(element, { ...memoizedItemData, element });
          }
          return next.sort(sortByDocumentPosition);
        });
      });
      React22.useEffect(() => {
        return () => {
          const registered = registeredRef.current;
          registeredRef.current = null;
          if (!registered) {
            return;
          }
          setCollection((map) => {
            if (!map.has(registered.element)) {
              return map;
            }
            const next = new OrderedDict(map);
            next.delete(registered.element);
            return next;
          });
        };
      }, [setCollection]);
      return (0, import_jsx_runtime3.jsx)(CollectionItemSlotImpl, { ...{ [ITEM_DATA_ATTR]: "" }, ref: composedRefs, children });
    }
  );
  CollectionItemSlot.displayName = ITEM_SLOT_NAME;
  function useInitCollection() {
    return React22.useState(new OrderedDict());
  }
  __name4(useInitCollection, "useInitCollection");
  function useCollection(scope) {
    const { collection } = useStatefulCollectionContext(name + "CollectionConsumer", scope);
    return collection;
  }
  __name4(useCollection, "useCollection");
  function useGetCollection(scope) {
    const { getCollection } = useStableCollectionContext(name + "CollectionConsumer", scope);
    return getCollection;
  }
  __name4(useGetCollection, "useGetCollection");
  const functions = {
    createCollectionScope,
    useCollection,
    useGetCollection,
    useInitCollection
  };
  return [
    { Provider: CollectionProvider, Slot: CollectionSlot, ItemSlot: CollectionItemSlot },
    functions
  ];
}
__name4(createCollection2, "createCollection");
function shallowEqual(a, b) {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object") return false;
  if (a == null || b == null) return false;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  for (const key of keysA) {
    if (!Object.prototype.hasOwnProperty.call(b, key)) return false;
    if (a[key] !== b[key]) return false;
  }
  return true;
}
__name4(shallowEqual, "shallowEqual");
function isElementPreceding(a, b) {
  return !!(b.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_PRECEDING);
}
__name4(isElementPreceding, "isElementPreceding");
function isInDocumentOrder(dict) {
  let previous;
  for (const element of dict.keys()) {
    if (previous) {
      const position = previous.compareDocumentPosition(element);
      if (!(position & Node.DOCUMENT_POSITION_DISCONNECTED) && position & Node.DOCUMENT_POSITION_PRECEDING) {
        return false;
      }
    }
    previous = element;
  }
  return true;
}
__name4(isInDocumentOrder, "isInDocumentOrder");
function sortByDocumentPosition(a, b) {
  return !a[1].element || !b[1].element ? 0 : isElementPreceding(a[1].element, b[1].element) ? -1 : 1;
}
__name4(sortByDocumentPosition, "sortByDocumentPosition");
function getChildListObserver(callback) {
  const observer = new MutationObserver((mutationsList) => {
    for (const mutation of mutationsList) {
      if (mutation.type === "childList") {
        callback();
        return;
      }
    }
  });
  return observer;
}
__name4(getChildListObserver, "getChildListObserver");

// node_modules/@radix-ui/primitive/dist/index.mjs
var __defProp5 = Object.defineProperty;
var __name5 = (target, value) => __defProp5(target, "name", { value, configurable: true });
var canUseDOM = !!(typeof window !== "undefined" && window.document && window.document.createElement);
function composeEventHandlers(originalEventHandler, ourEventHandler, { checkForDefaultPrevented = true } = {}) {
  return __name5(function handleEvent(event) {
    originalEventHandler?.(event);
    if (checkForDefaultPrevented === false || !event || !event.defaultPrevented) {
      return ourEventHandler?.(event);
    }
  }, "handleEvent");
}
__name5(composeEventHandlers, "composeEventHandlers");
function getOwnerWindow(element) {
  if (!canUseDOM) {
    throw new Error("Cannot access window outside of the DOM");
  }
  return element?.ownerDocument?.defaultView ?? window;
}
__name5(getOwnerWindow, "getOwnerWindow");
function getOwnerDocument(element) {
  if (!canUseDOM) {
    throw new Error("Cannot access document outside of the DOM");
  }
  return element?.ownerDocument ?? document;
}
__name5(getOwnerDocument, "getOwnerDocument");
function getActiveElement(node, activeDescendant = false) {
  const { activeElement } = getOwnerDocument(node);
  if (!activeElement?.nodeName) {
    return null;
  }
  if (isFrame(activeElement) && activeElement.contentDocument) {
    return getActiveElement(activeElement.contentDocument.body, activeDescendant);
  }
  if (activeDescendant) {
    const id = activeElement.getAttribute("aria-activedescendant");
    if (id) {
      const element = getOwnerDocument(activeElement).getElementById(id);
      if (element) {
        return element;
      }
    }
  }
  return activeElement;
}
__name5(getActiveElement, "getActiveElement");
function isFrame(element) {
  return element.tagName === "IFRAME";
}
__name5(isFrame, "isFrame");

// node_modules/@radix-ui/react-use-controllable-state/dist/index.mjs
var React7 = __toESM(require_react(), 1);

// node_modules/@radix-ui/primitive/dist/internal/is-development.true.mjs
var IS_DEVELOPMENT = true;

// node_modules/@radix-ui/react-use-controllable-state/dist/index.mjs
var React23 = __toESM(require_react(), 1);

// node_modules/@radix-ui/react-use-effect-event/dist/index.mjs
var React6 = __toESM(require_react(), 1);
var __defProp6 = Object.defineProperty;
var __name6 = (target, value) => __defProp6(target, "name", { value, configurable: true });
var useReactEffectEvent = React6[" useEffectEvent ".trim().toString()];
var useReactInsertionEffect = React6[" useInsertionEffect ".trim().toString()];
function useEffectEvent(callback) {
  if (typeof useReactEffectEvent === "function") {
    return useReactEffectEvent(callback);
  }
  const ref = React6.useRef(() => {
    throw new Error("Cannot call an event handler while rendering.");
  });
  if (typeof useReactInsertionEffect === "function") {
    useReactInsertionEffect(() => {
      ref.current = callback;
    });
  } else {
    useLayoutEffect2(() => {
      ref.current = callback;
    });
  }
  return React6.useMemo(() => ((...args) => ref.current?.(...args)), []);
}
__name6(useEffectEvent, "useEffectEvent");

// node_modules/@radix-ui/react-use-controllable-state/dist/index.mjs
var __defProp7 = Object.defineProperty;
var __name7 = (target, value) => __defProp7(target, "name", { value, configurable: true });
var useInsertionEffect = React7[" useInsertionEffect ".trim().toString()] || useLayoutEffect2;
function useControllableState({
  prop,
  defaultProp,
  onChange = __name7(() => {
  }, "onChange"),
  caller
}) {
  const [uncontrolledProp, setUncontrolledProp, onChangeRef] = useUncontrolledState({
    defaultProp,
    onChange
  });
  const isControlled = prop !== void 0;
  const value = isControlled ? prop : uncontrolledProp;
  if (IS_DEVELOPMENT) {
    const isControlledRef = React7.useRef(prop !== void 0);
    React7.useEffect(() => {
      const wasControlled = isControlledRef.current;
      if (wasControlled !== isControlled) {
        const from = wasControlled ? "controlled" : "uncontrolled";
        const to = isControlled ? "controlled" : "uncontrolled";
        console.warn(
          `${caller} is changing from ${from} to ${to}. Components should not switch from controlled to uncontrolled (or vice versa). Decide between using a controlled or uncontrolled value for the lifetime of the component.`
        );
      }
      isControlledRef.current = isControlled;
    }, [isControlled, caller]);
  }
  const setValue = React7.useCallback(
    (nextValue) => {
      if (isControlled) {
        const value2 = isFunction(nextValue) ? nextValue(prop) : nextValue;
        if (value2 !== prop) {
          onChangeRef.current?.(value2);
        }
      } else {
        setUncontrolledProp(nextValue);
      }
    },
    [isControlled, prop, setUncontrolledProp, onChangeRef]
  );
  return [value, setValue];
}
__name7(useControllableState, "useControllableState");
function useUncontrolledState({
  defaultProp,
  onChange
}) {
  const [value, setValue] = React7.useState(defaultProp);
  const prevValueRef = React7.useRef(value);
  const onChangeRef = React7.useRef(onChange);
  useInsertionEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);
  React7.useEffect(() => {
    if (prevValueRef.current !== value) {
      onChangeRef.current?.(value);
      prevValueRef.current = value;
    }
  }, [value, prevValueRef]);
  return [value, setValue, onChangeRef];
}
__name7(useUncontrolledState, "useUncontrolledState");
function isFunction(value) {
  return typeof value === "function";
}
__name7(isFunction, "isFunction");
var SYNC_STATE = /* @__PURE__ */ Symbol("RADIX:SYNC_STATE");
function useControllableStateReducer(reducer, userArgs, initialArg, init) {
  const { prop: controlledState, defaultProp, onChange: onChangeProp, caller } = userArgs;
  const isControlled = controlledState !== void 0;
  const onChange = useEffectEvent(onChangeProp);
  if (IS_DEVELOPMENT) {
    const isControlledRef = React23.useRef(controlledState !== void 0);
    React23.useEffect(() => {
      const wasControlled = isControlledRef.current;
      if (wasControlled !== isControlled) {
        const from = wasControlled ? "controlled" : "uncontrolled";
        const to = isControlled ? "controlled" : "uncontrolled";
        console.warn(
          `${caller} is changing from ${from} to ${to}. Components should not switch from controlled to uncontrolled (or vice versa). Decide between using a controlled or uncontrolled value for the lifetime of the component.`
        );
      }
      isControlledRef.current = isControlled;
    }, [isControlled, caller]);
  }
  const args = [{ ...initialArg, state: defaultProp }];
  if (init) {
    args.push(init);
  }
  const [internalState, dispatch] = React23.useReducer(
    (state2, action) => {
      if (action.type === SYNC_STATE) {
        return { ...state2, state: action.state };
      }
      const next = reducer(state2, action);
      if (isControlled && !Object.is(next.state, state2.state)) {
        onChange(next.state);
      }
      return next;
    },
    ...args
  );
  const uncontrolledState = internalState.state;
  const prevValueRef = React23.useRef(uncontrolledState);
  React23.useEffect(() => {
    if (prevValueRef.current !== uncontrolledState) {
      prevValueRef.current = uncontrolledState;
      if (!isControlled) {
        onChange(uncontrolledState);
      }
    }
  }, [uncontrolledState, prevValueRef, isControlled]);
  const state = React23.useMemo(() => {
    const isControlled2 = controlledState !== void 0;
    if (isControlled2) {
      return { ...internalState, state: controlledState };
    }
    return internalState;
  }, [internalState, controlledState]);
  React23.useEffect(() => {
    if (isControlled && !Object.is(controlledState, internalState.state)) {
      dispatch({ type: SYNC_STATE, state: controlledState });
    }
  }, [controlledState, internalState.state, isControlled]);
  return [state, dispatch];
}
__name7(useControllableStateReducer, "useControllableStateReducer");

// node_modules/@radix-ui/react-primitive/dist/index.mjs
var React8 = __toESM(require_react(), 1);
var ReactDOM = __toESM(require_react_dom(), 1);
var import_jsx_runtime4 = __toESM(require_jsx_runtime(), 1);
var __defProp8 = Object.defineProperty;
var __name8 = (target, value) => __defProp8(target, "name", { value, configurable: true });
var NODES = [
  "a",
  "button",
  "div",
  "form",
  "h2",
  "h3",
  "img",
  "input",
  "label",
  "li",
  "nav",
  "ol",
  "p",
  "select",
  "span",
  "svg",
  "ul"
];
var Primitive = NODES.reduce((primitive, node) => {
  const Slot2 = createSlot(`Primitive.${node}`);
  const Node2 = React8.forwardRef((props, forwardedRef) => {
    const { asChild, ...primitiveProps } = props;
    const Comp = asChild ? Slot2 : node;
    if (typeof window !== "undefined") {
      window[/* @__PURE__ */ Symbol.for("radix-ui")] = true;
    }
    return (0, import_jsx_runtime4.jsx)(Comp, { ...primitiveProps, ref: forwardedRef });
  });
  Node2.displayName = `Primitive.${node}`;
  return { ...primitive, [node]: Node2 };
}, {});
function dispatchDiscreteCustomEvent(target, event) {
  if (target) ReactDOM.flushSync(() => target.dispatchEvent(event));
}
__name8(dispatchDiscreteCustomEvent, "dispatchDiscreteCustomEvent");

// node_modules/@radix-ui/react-id/dist/index.mjs
var React9 = __toESM(require_react(), 1);
var __defProp9 = Object.defineProperty;
var __name9 = (target, value) => __defProp9(target, "name", { value, configurable: true });
var useReactId = React9[" useId ".trim().toString()] || (() => void 0);
var count = 0;
function useId(deterministicId) {
  const [id, setId] = React9.useState(useReactId());
  useLayoutEffect2(() => {
    if (!deterministicId) setId((reactId) => reactId ?? String(count++));
  }, [deterministicId]);
  return deterministicId || (id ? `radix-${id}` : "");
}
__name9(useId, "useId");

// node_modules/@radix-ui/react-direction/dist/index.mjs
var React10 = __toESM(require_react(), 1);
var import_jsx_runtime5 = __toESM(require_jsx_runtime(), 1);
var __defProp10 = Object.defineProperty;
var __name10 = (target, value) => __defProp10(target, "name", { value, configurable: true });
var Direction = {
  LTR: "ltr",
  RTL: "rtl"
};
var DirectionContext = React10.createContext(void 0);
var DirectionProvider = __name10((props) => {
  const { dir, children } = props;
  return (0, import_jsx_runtime5.jsx)(DirectionContext.Provider, { value: dir, children });
}, "DirectionProvider");
function useDirection(localDir) {
  const globalDir = React10.useContext(DirectionContext);
  return localDir || globalDir || Direction.LTR;
}
__name10(useDirection, "useDirection");

// node_modules/@radix-ui/react-presence/dist/index.mjs
var React24 = __toESM(require_react(), 1);
var React11 = __toESM(require_react(), 1);
var __defProp11 = Object.defineProperty;
var __name11 = (target, value) => __defProp11(target, "name", { value, configurable: true });
function useStateMachine(initialState, machine) {
  return React11.useReducer((state, event) => {
    const nextState = machine[state][event];
    return nextState ?? state;
  }, initialState);
}
__name11(useStateMachine, "useStateMachine");
var Presence = __name11((props) => {
  const { present, children } = props;
  const presence = usePresence(present);
  const child = typeof children === "function" ? children({ present: presence.isPresent }) : React24.Children.only(children);
  const ref = useStableComposedRefs(presence.ref, getElementRef2(child));
  const forceMount = typeof children === "function";
  return forceMount || presence.isPresent ? React24.cloneElement(child, { ref }) : null;
}, "Presence");
function usePresence(present) {
  const [node, setNode] = React24.useState();
  const stylesRef = React24.useRef(null);
  const prevPresentRef = React24.useRef(present);
  const prevAnimationNameRef = React24.useRef("none");
  const mountAnimationNameRef = React24.useRef(void 0);
  const initialState = present ? "mounted" : "unmounted";
  const [state, send] = useStateMachine(initialState, {
    mounted: {
      UNMOUNT: "unmounted",
      ANIMATION_OUT: "unmountSuspended"
    },
    unmountSuspended: {
      MOUNT: "mounted",
      ANIMATION_END: "unmounted"
    },
    unmounted: {
      MOUNT: "mounted"
    }
  });
  React24.useEffect(() => {
    if (state === "mounted") {
      prevAnimationNameRef.current = mountAnimationNameRef.current ?? getAnimationName(stylesRef.current);
      mountAnimationNameRef.current = void 0;
    } else {
      prevAnimationNameRef.current = "none";
    }
  }, [state]);
  useLayoutEffect2(() => {
    const styles = stylesRef.current;
    const wasPresent = prevPresentRef.current;
    const hasPresentChanged = wasPresent !== present;
    if (hasPresentChanged) {
      const prevAnimationName = prevAnimationNameRef.current;
      const currentAnimationName = getAnimationName(styles);
      if (present) {
        mountAnimationNameRef.current = currentAnimationName;
        send("MOUNT");
      } else if (currentAnimationName === "none" || styles?.display === "none") {
        send("UNMOUNT");
      } else {
        const isAnimating = prevAnimationName !== currentAnimationName;
        if (wasPresent && isAnimating) {
          send("ANIMATION_OUT");
        } else {
          send("UNMOUNT");
        }
      }
      prevPresentRef.current = present;
    }
  }, [present, send]);
  useLayoutEffect2(() => {
    if (node) {
      let timeoutId;
      const ownerWindow = node.ownerDocument.defaultView ?? window;
      const handleAnimationEnd = __name11((event) => {
        const currentAnimationName = getAnimationName(stylesRef.current);
        const isCurrentAnimation = currentAnimationName.includes(CSS.escape(event.animationName));
        if (event.target === node && isCurrentAnimation) {
          send("ANIMATION_END");
          if (!prevPresentRef.current) {
            const currentFillMode = node.style.animationFillMode;
            node.style.animationFillMode = "forwards";
            timeoutId = ownerWindow.setTimeout(() => {
              if (node.style.animationFillMode === "forwards") {
                node.style.animationFillMode = currentFillMode;
              }
            });
          }
        }
      }, "handleAnimationEnd");
      const handleAnimationStart = __name11((event) => {
        if (event.target === node) {
          prevAnimationNameRef.current = getAnimationName(stylesRef.current);
        }
      }, "handleAnimationStart");
      node.addEventListener("animationstart", handleAnimationStart);
      node.addEventListener("animationcancel", handleAnimationEnd);
      node.addEventListener("animationend", handleAnimationEnd);
      return () => {
        ownerWindow.clearTimeout(timeoutId);
        node.removeEventListener("animationstart", handleAnimationStart);
        node.removeEventListener("animationcancel", handleAnimationEnd);
        node.removeEventListener("animationend", handleAnimationEnd);
      };
    } else {
      send("ANIMATION_END");
    }
  }, [node, send]);
  return {
    isPresent: ["mounted", "unmountSuspended"].includes(state),
    ref: React24.useCallback((node2) => {
      if (node2) {
        const styles = getComputedStyle(node2);
        stylesRef.current = styles;
        mountAnimationNameRef.current = getAnimationName(styles);
      } else {
        stylesRef.current = null;
      }
      setNode(node2);
    }, [])
  };
}
__name11(usePresence, "usePresence");
function setRef2(ref, value) {
  if (typeof ref === "function") {
    return ref(value);
  } else if (ref !== null && ref !== void 0) {
    ref.current = value;
  }
}
__name11(setRef2, "setRef");
function useStableComposedRefs(...refs) {
  const refsRef = React24.useRef(refs);
  refsRef.current = refs;
  return React24.useCallback((node) => {
    const currentRefs = refsRef.current;
    let hasCleanup = false;
    const cleanups = currentRefs.map((ref) => {
      const cleanup = setRef2(ref, node);
      if (!hasCleanup && typeof cleanup === "function") {
        hasCleanup = true;
      }
      return cleanup;
    });
    if (hasCleanup) {
      return () => {
        for (let i = 0; i < cleanups.length; i++) {
          const cleanup = cleanups[i];
          if (typeof cleanup === "function") {
            cleanup();
          } else {
            setRef2(currentRefs[i], null);
          }
        }
      };
    }
  }, []);
}
__name11(useStableComposedRefs, "useStableComposedRefs");
function getAnimationName(styles) {
  return styles?.animationName || "none";
}
__name11(getAnimationName, "getAnimationName");
function getElementRef2(element) {
  let getter = Object.getOwnPropertyDescriptor(element.props, "ref")?.get;
  let mayWarn = getter && "isReactWarning" in getter && getter.isReactWarning;
  if (mayWarn) {
    return element.ref;
  }
  getter = Object.getOwnPropertyDescriptor(element, "ref")?.get;
  mayWarn = getter && "isReactWarning" in getter && getter.isReactWarning;
  if (mayWarn) {
    return element.props.ref;
  }
  return element.props.ref || element.ref;
}
__name11(getElementRef2, "getElementRef");

export {
  createContextScope,
  useComposedRefs,
  createSlot,
  useLayoutEffect2,
  createCollection,
  createCollection2,
  composeEventHandlers,
  useControllableState,
  Primitive,
  dispatchDiscreteCustomEvent,
  Presence,
  useId,
  useDirection
};
//# sourceMappingURL=chunk-V4RPBO7K.js.map
