function result = buildPowerPolarLinearization(operatingPoint)
%BUILDPOWERPOLARLINEARIZATION Linearize dq/power-polar coordinates.
%   RESULT = BUILDPOWERPOLARLINEARIZATION(OPERATINGPOINT) returns the
%   matrices E, C, F and Finverse at a nonzero dq operating point:
%
%       delta[p;q] = E*delta[i_d;i_q] + C*delta[v_d;v_q]
%       delta[v_d;v_q] = F*delta[phi;|v|].
%
%   OPERATINGPOINT is a scalar struct with exactly the fields vd, vq, id
%   and iq. The reactive-power convention is
%       q = vq*id - vd*iq,
%   consistent with s = (vd+j*vq)*conj(id+j*iq).

    validateOperatingPoint(operatingPoint);

    vd = double(operatingPoint.vd);
    vq = double(operatingPoint.vq);
    id = double(operatingPoint.id);
    iq = double(operatingPoint.iq);
    voltageMagnitude = hypot(vd, vq);
    if voltageMagnitude == 0
        error('gfm:buildPowerPolarLinearization:ZeroVoltage', ...
            'The voltage operating point must be nonzero.');
    end

    E = [vd, vq; vq, -vd];
    C = [id, iq; -iq, id];
    F = [-vq, vd/voltageMagnitude; ...
        vd, vq/voltageMagnitude];
    Finverse = [-vq/voltageMagnitude^2, ...
        vd/voltageMagnitude^2; ...
        vd/voltageMagnitude, vq/voltageMagnitude];
    inverseResidual = norm(Finverse*F-eye(2), 'fro');

    result = struct( ...
        'E', E, ...
        'C', C, ...
        'F', F, ...
        'Finverse', Finverse, ...
        'voltageMagnitude', voltageMagnitude, ...
        'voltageAngle', atan2(vq, vd), ...
        'inverseResidual', inverseResidual, ...
        'operatingPoint', operatingPoint, ...
        'powerConvention', "s=v*conj(i); q=vq*id-vd*iq", ...
        'method', "power-polar-linearization-v1");
end

function validateOperatingPoint(operatingPoint)
    if ~(isstruct(operatingPoint) && isscalar(operatingPoint))
        error('gfm:buildPowerPolarLinearization:InvalidOperatingPoint', ...
            'operatingPoint must be a scalar struct.');
    end
    requiredNames = {'vd', 'vq', 'id', 'iq'};
    actualNames = fieldnames(operatingPoint);
    missingNames = setdiff(requiredNames, actualNames);
    unknownNames = setdiff(actualNames, requiredNames);
    if ~isempty(missingNames)
        error('gfm:buildPowerPolarLinearization:MissingField', ...
            'Missing operating-point field: %s.', missingNames{1});
    end
    if ~isempty(unknownNames)
        error('gfm:buildPowerPolarLinearization:UnknownField', ...
            'Unknown operating-point field: %s.', unknownNames{1});
    end
    for index = 1:numel(requiredNames)
        name = requiredNames{index};
        value = operatingPoint.(name);
        if ~(isnumeric(value) && isreal(value) && isscalar(value) && ...
                isfinite(value))
            error('gfm:buildPowerPolarLinearization:InvalidField', ...
                '%s must be a finite real scalar.', name);
        end
    end
end
