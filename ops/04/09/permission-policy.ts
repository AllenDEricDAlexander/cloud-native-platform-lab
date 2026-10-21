// 合入固定版本的Backstage backend模块，通过policyExtensionPoint.setPolicy注册。
import { AuthorizeResult, type PolicyDecision } from '@backstage/plugin-permission-common';
import type { PermissionPolicy, PolicyQuery, PolicyQueryUser } from '@backstage/plugin-permission-node';

export const cnplPermissionPolicy: PermissionPolicy = {
    async handle(_request: PolicyQuery, user?: PolicyQueryUser): Promise<PolicyDecision> {
        const allowed = user?.info.ownershipEntityRefs.includes('group:default/platform') ?? false;
        return { result: allowed ? AuthorizeResult.ALLOW : AuthorizeResult.DENY };
    },
};
