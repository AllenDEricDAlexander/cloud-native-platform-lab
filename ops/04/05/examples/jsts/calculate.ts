export function calculate(value: number): number {
    if (!Number.isFinite(value)) throw new Error('Finite input required');
    return value * value;
}
