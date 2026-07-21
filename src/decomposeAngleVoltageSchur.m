function result = decomposeAngleVoltageSchur(matrix, options)
%DECOMPOSEANGLEVOLTAGESCHUR Split a 2-by-2 angle-voltage return matrix.
%   RESULT = DECOMPOSEANGLEVOLTAGESCHUR(MATRIX) partitions MATRIX as
%   [A B; C D] and forms the voltage-pivot Schur complement A-B*D^(-1)*C.
%   MATRIX may be numeric or a 2-by-2 dynamic-system array.

    arguments
        matrix
        options.PivotTolerance (1, 1) double {mustBeNonnegative} = 0
        options.Pivot (1, 1) string {mustBeMember(options.Pivot, ...
            ["voltage", "angle"])} = "voltage"
    end

    if ~isequal(size(matrix), [2, 2])
        error('SchurAngleVoltage:InvalidSize', ...
            'Input must be a 2-by-2 matrix or dynamic-system array.');
    end

    angleBlock = matrix(1, 1);
    angleToVoltage = matrix(1, 2);
    voltageToAngle = matrix(2, 1);
    voltageBlock = matrix(2, 2);

    if options.Pivot == "voltage"
        pivotBlock = voltageBlock;
        retainedBlock = angleBlock;
        leftCoupling = angleToVoltage;
        rightCoupling = voltageToAngle;
    else
        pivotBlock = angleBlock;
        retainedBlock = voltageBlock;
        leftCoupling = voltageToAngle;
        rightCoupling = angleToVoltage;
    end

    if isnumeric(matrix)
        if any(~isfinite(matrix), 'all')
            error('SchurAngleVoltage:NonfiniteInput', ...
                'Numeric input must contain only finite values.');
        end
        scale = max(1, norm(matrix, 2));
        if abs(pivotBlock) <= options.PivotTolerance * scale
            error('SchurAngleVoltage:SingularPivot', ...
                'The requested Schur pivot is singular at the requested tolerance.');
        end
        schurComplement = retainedBlock - leftCoupling * ...
            (rightCoupling / pivotBlock);
        characteristicDeterminant = angleBlock * voltageBlock - ...
            angleToVoltage * voltageToAngle;
        factorizationResidual = characteristicDeterminant - ...
            pivotBlock * schurComplement;
    else
        % Keep the raw rational expressions. A Schur complement can be
        % improper even when the full transfer matrix is proper, and minreal
        % does not accept such intermediate models. Pointwise evaluation is
        % the reliable representation-independent check in that case.
        schurComplement = retainedBlock - leftCoupling * ...
            (rightCoupling / pivotBlock);
        characteristicDeterminant = angleBlock * voltageBlock - ...
            angleToVoltage * voltageToAngle;
        factorizationResidual = characteristicDeterminant - ...
            pivotBlock * schurComplement;
    end

    result = struct( ...
        'angleBlock', angleBlock, ...
        'angleToVoltage', angleToVoltage, ...
        'voltageToAngle', voltageToAngle, ...
        'voltageBlock', voltageBlock, ...
        'pivotName', options.Pivot, ...
        'pivotBlock', pivotBlock, ...
        'schurComplement', schurComplement, ...
        'characteristicDeterminant', characteristicDeterminant, ...
        'factorizationResidual', factorizationResidual);
end
